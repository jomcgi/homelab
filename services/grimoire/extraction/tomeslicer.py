#!/usr/bin/env python3
"""
TomeSlicer — D&D PDF extraction pipeline.

Two-stage pipeline:
  Stage 1: Marker (Surya OCR/layout) for spatial extraction (boxes, text, reading order)
  Stage 2: Gemini Flash for D&D semantic enrichment (types, visibility, entities)

Usage:
  python tomeslicer.py extract-page book.pdf --page 10
  python tomeslicer.py extract-pdf book.pdf --limit 10
  python tomeslicer.py evaluate page.png output.json
  python tomeslicer.py annotate page.png output.json

Requirements:
  pip install pydantic typer Pillow marker-pdf google-genai
"""

import json
import os
import re
import tempfile
from enum import Enum
from html import unescape
from pathlib import Path
from typing import Optional, Annotated, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import typer
from pydantic import BaseModel, Field, field_validator

app = typer.Typer(help="TomeSlicer — D&D PDF extraction pipeline")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATA MODEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BlockType(str, Enum):
    # Structural (depth 0-2)
    CHAPTER_HEADING = "chapter_heading"
    SECTION_HEADING = "section_heading"
    SUBSECTION_HEADING = "subsection_heading"
    PAGE_FOOTER = "page_footer"

    # Prose (depth 3)
    BODY_TEXT = "body_text"
    READ_ALOUD = "read_aloud"
    LORE_SIDEBAR = "lore_sidebar"
    DM_GUIDANCE = "dm_guidance"

    # Game mechanics (depth 3)
    STAT_BLOCK = "stat_block"
    SPELL_DESCRIPTION = "spell_description"
    ITEM_DESCRIPTION = "item_description"
    CLASS_FEATURE = "class_feature"
    RACE_TRAIT = "race_trait"
    FEAT_DESCRIPTION = "feat_description"
    RULE_CALLOUT = "rule_callout"

    # Tabular (depth 3)
    TABLE = "table"

    # Visual (depth 3, no text)
    MAP = "map"
    ILLUSTRATION = "illustration"
    HANDOUT = "handout"

    # Blank / decorative (depth 0, no text)
    BLANK_PAGE = "blank_page"


BLOCK_DEPTH: dict[BlockType, int] = {
    BlockType.CHAPTER_HEADING: 0,
    BlockType.SECTION_HEADING: 1,
    BlockType.SUBSECTION_HEADING: 2,
    BlockType.PAGE_FOOTER: 0,
    BlockType.BLANK_PAGE: 0,
}


def get_depth(block_type: BlockType) -> int:
    return BLOCK_DEPTH.get(block_type, 3)


class Visibility(str, Enum):
    DM_ONLY = "dm_only"  # Secrets, monster stats, DC checks, trap triggers
    PLAYER_KNOWN = (
        "player_known"  # General rules, public world lore, player-facing tables
    )
    PLAYER_REVEALABLE = (
        "player_revealable"  # Read-aloud text, handout text, discovered item properties
    )


class ExtractionBlock(BaseModel):
    type: BlockType
    label: Annotated[str, Field(max_length=80)]
    text: str = ""
    html: str = ""
    box_2d: list[int] = Field(min_length=4, max_length=4)

    visibility: Visibility = Visibility.DM_ONLY
    entities: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("box_2d")
    @classmethod
    def validate_box(cls, v: list[int]) -> list[int]:
        if len(v) != 4:
            raise ValueError(f"box_2d must have exactly 4 values, got {len(v)}")
        y_min, x_min, y_max, x_max = v
        for c in v:
            if not (0 <= c <= 1000):
                raise ValueError(f"box_2d coordinate {c} outside 0-1000 range")
        if y_min >= y_max:
            raise ValueError(f"box_2d y_min ({y_min}) >= y_max ({y_max})")
        if x_min >= x_max:
            raise ValueError(f"box_2d x_min ({x_min}) >= x_max ({x_max})")
        return v

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str, info) -> str:
        block_type = info.data.get("type")
        visual_types = {
            BlockType.MAP,
            BlockType.ILLUSTRATION,
            BlockType.HANDOUT,
            BlockType.BLANK_PAGE,
        }
        if block_type not in visual_types and not v.strip():
            raise ValueError(
                f"Non-visual block type '{block_type}' requires non-empty text"
            )
        return v

    @property
    def depth(self) -> int:
        return get_depth(self.type)

    @property
    def is_heading(self) -> bool:
        return self.type in {
            BlockType.CHAPTER_HEADING,
            BlockType.SECTION_HEADING,
            BlockType.SUBSECTION_HEADING,
        }

    @property
    def is_content(self) -> bool:
        return self.depth == 3 and self.type != BlockType.PAGE_FOOTER

    @property
    def heading_level(self) -> Optional[int]:
        """Returns the exact depth (1-6) of the heading based on markdown, or None."""
        if not self.is_heading:
            return None
        # Count the leading '#' characters in the text
        import re

        match = re.match(r"^(#+)\s", self.text)
        if match:
            return len(match.group(1))

        # Fallback to your BLOCK_DEPTH dictionary if no markdown hashes are present
        return self.depth + 1


class PageExtraction(BaseModel):
    blocks: list[ExtractionBlock] = Field(min_length=1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENRICHMENT MODELS (Stage 2 — Gemini response schema)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BlockEnrichment(BaseModel):
    block_index: int
    type: BlockType
    label: Annotated[str, Field(max_length=80)]
    visibility: Visibility = Visibility.DM_ONLY
    entities: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("entities", mode="before")
    @classmethod
    def coerce_entities(cls, v):
        return v if v is not None else []

    @field_validator("attributes", mode="before")
    @classmethod
    def coerce_attributes(cls, v):
        return v if v is not None else {}


class PageEnrichment(BaseModel):
    blocks: list[BlockEnrichment]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MARKER INTEGRATION (Stage 1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MARKER_TYPE_MAP = {
    "SectionHeader": "section_heading",
    "Text": "body_text",
    "TextInlineMath": "body_text",
    "Table": "table",
    "Figure": "illustration",
    "Picture": "illustration",
    "Caption": "body_text",
    "Code": "body_text",
    "Equation": "rule_callout",
    "Form": "table",
    "Footnote": "page_footer",
    "PageFooter": "page_footer",
    "PageHeader": "page_footer",
    "ListGroup": "body_text",
    "ListItem": "body_text",
    "HandwrittenText": "body_text",
}

_marker_models = None


def get_marker_models():
    """Singleton loader for Surya models. Lazy-imported, loaded once."""
    global _marker_models
    if _marker_models is None:
        from marker.models import (
            create_model_dict,
        )  # gazelle:ignore marker.models,marker

        _marker_models = create_model_dict()
    return _marker_models


def html_to_text(html: str) -> str:
    """Convert Marker HTML output to markdown-formatted text."""
    text = html
    for i in range(1, 7):
        text = re.sub(
            rf"<h{i}[^>]*>(.*?)</h{i}>",
            rf"{'#' * i} \1\n",
            text,
            flags=re.DOTALL,
        )
    text = re.sub(r"<(b|strong)[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL)
    text = re.sub(r"<(i|em)[^>]*>(.*?)</\1>", r"*\2*", text, flags=re.DOTALL)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL)
    text = re.sub(r"</?[ou]l[^>]*>", "\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<p[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_table_to_markdown(html: str) -> str:
    """Convert HTML table to GitHub Flavored Markdown table."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.DOTALL)
    if not rows:
        return html_to_text(html)
    md_rows = []
    for row in rows:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.DOTALL)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        cells = [unescape(c) for c in cells]
        md_rows.append("| " + " | ".join(cells) + " |")
    if md_rows:
        num_cols = md_rows[0].count("|") - 1
        separator = "| " + " | ".join(["---"] * max(num_cols, 1)) + " |"
        md_rows.insert(1, separator)
    return "\n".join(md_rows)


def convert_marker_block(block, page_width: float, page_height: float) -> dict:
    """Convert a Marker JSON block to TomeSlicer intermediate format."""
    from marker.output import json_to_html  # gazelle:ignore marker.output,marker

    polygon = block.polygon
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    box_2d = [
        max(0, min(1000, int(y_min / page_height * 1000))),
        max(0, min(1000, int(x_min / page_width * 1000))),
        max(0, min(1000, int(y_max / page_height * 1000))),
        max(0, min(1000, int(x_max / page_width * 1000))),
    ]
    # Ensure valid box (y_min < y_max, x_min < x_max)
    if box_2d[0] >= box_2d[2]:
        box_2d[2] = min(1000, box_2d[0] + 1)
    if box_2d[1] >= box_2d[3]:
        box_2d[3] = min(1000, box_2d[1] + 1)

    bt = block.block_type
    block_type_str = bt.name if hasattr(bt, "name") else str(bt).split(".")[-1]

    full_html = json_to_html(block)
    if block_type_str == "Table":
        text = html_table_to_markdown(full_html)
    else:
        text = html_to_text(full_html)

    preliminary_type = MARKER_TYPE_MAP.get(block_type_str, "body_text")

    return {
        "text": text,
        "box_2d": box_2d,
        "html": full_html,
        "preliminary_type": preliminary_type,
        "marker_block_type": block_type_str,
    }


def extract_with_marker(
    pdf_path: Path, page_range: list[int] | None = None
) -> list[dict]:
    """
    Run Marker on a PDF. Returns list of page dicts with blocks.

    Args:
        pdf_path: Path to PDF file
        page_range: Optional list of 0-indexed page numbers to process

    Returns:
        List of dicts: {page_number, page_width, page_height, blocks: [...]}
    """
    from marker.converters.pdf import (
        PdfConverter,
    )  # gazelle:ignore marker.converters.pdf,marker.converters,marker
    from marker.config.parser import (
        ConfigParser,
    )  # gazelle:ignore marker.config.parser,marker.config,marker

    config = {"output_format": "json"}
    if page_range is not None:
        config["page_range"] = ",".join(str(p) for p in page_range)

    config_parser = ConfigParser(config)
    converter = PdfConverter(
        config=config_parser.generate_config_dict(),
        artifact_dict=get_marker_models(),
        renderer=config_parser.get_renderer(),
    )

    rendered = converter(str(pdf_path))

    pages = []
    for page_idx, page in enumerate(rendered.children):
        bbox = page.bbox
        page_width = bbox[2] - bbox[0]
        page_height = bbox[3] - bbox[1]

        blocks = []
        for child in page.children:
            block_dict = convert_marker_block(child, page_width, page_height)
            blocks.append(block_dict)

        actual_page_num = (page_range[page_idx] + 1) if page_range else (page_idx + 1)
        pages.append(
            {
                "page_number": actual_page_num,
                "page_width": page_width,
                "page_height": page_height,
                "blocks": blocks,
            }
        )

    return pages


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENRICHMENT PIPELINE (Stage 2 — Gemini)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ENRICHMENT_MODEL = "gemini-3-flash-preview"

ENRICHMENT_SYSTEM_PROMPT = """You are a D&D 5th Edition content classifier. You receive pre-extracted text blocks from a book page and classify them with D&D-specific metadata.

For each block, determine:
1. TYPE: The specific D&D block type from the allowed list
2. LABEL: A short descriptive label (max 80 chars)
3. VISIBILITY: How this content should be routed in a VTT
4. ENTITIES: Named proper nouns (NPCs, factions, monsters, spells, items, locations)
5. ATTRIBUTES: Structured data for mechanical blocks

## Block Types
STRUCTURAL: "chapter_heading", "section_heading", "subsection_heading", "page_footer"
PROSE: "body_text", "read_aloud" (tan/beige boxes OR italicized atmospheric flavor text), "lore_sidebar", "dm_guidance"
GAME MECHANICS: "stat_block", "spell_description", "item_description", "class_feature", "race_trait", "feat_description", "rule_callout"
OTHER: "table", "map", "illustration", "handout", "blank_page"

## Visibility Routing
- "dm_only": Hidden mechanics, trap triggers, stat blocks, DC checks, DM guidance, and setting secrets.
- "player_known": Player-facing rules, class features, spells, race traits, standard lore.
- "player_revealable": Read-aloud text, handout text, room descriptions before secrets.

## Entity Extraction
Extract specific proper nouns: Named NPCs, Factions (e.g., “Clovis Concord”), Monster Types, Spells, Magic Items, Locations.

Return a JSON object with a “blocks” array. Each entry MUST include block_index matching the input block number.
"""

_genai_client = None


def get_genai_client():
    """Singleton Gemini client. Uses GOOGLE_API_KEY env var."""
    global _genai_client
    if _genai_client is None:
        if not os.environ.get("GOOGLE_API_KEY"):
            raise RuntimeError(
                "GOOGLE_API_KEY environment variable not set. "
                "Required for Gemini enrichment."
            )
        from google import genai  # gazelle:ignore google

        _genai_client = genai.Client()
    return _genai_client


def enrich_page_blocks(
    blocks: list[dict],
    page_number: int,
    model: str = ENRICHMENT_MODEL,
    max_retries: int = 2,
) -> PageEnrichment | None:
    """Send page blocks to Gemini for D&D semantic enrichment."""
    from google.genai import types  # gazelle:ignore google.genai,google

    client = get_genai_client()

    block_descriptions = []
    for i, block in enumerate(blocks):
        text_preview = block["text"][:1000] if block["text"] else "(no text)"
        desc = f"Block {i} [{block['preliminary_type']}]:\n{text_preview}"
        block_descriptions.append(desc)

    prompt = (
        f"Page {page_number}. Classify these {len(blocks)} D&D content blocks.\n\n"
        + "\n\n---\n\n".join(block_descriptions)
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=ENRICHMENT_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )
            return PageEnrichment.model_validate_json(response.text)
        except Exception as e:
            typer.echo(
                f"  [{attempt}/{max_retries}] Enrichment error (page {page_number}): {e}",
                err=True,
            )

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MERGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def merge_marker_and_enrichment(
    marker_blocks: list[dict],
    enrichment: PageEnrichment | None,
) -> list[dict]:
    """
    Combine Marker spatial data with Gemini enrichment.
    Falls back to preliminary types if enrichment is None.
    """
    enrich_map: dict[int, BlockEnrichment] = {}
    if enrichment:
        for be in enrichment.blocks:
            enrich_map[be.block_index] = be

    merged = []
    for i, mb in enumerate(marker_blocks):
        be = enrich_map.get(i)
        if be:
            block = {
                "type": be.type.value,
                "label": be.label,
                "text": mb["text"],
                "html": mb["html"],
                "box_2d": mb["box_2d"],
                "visibility": be.visibility.value,
                "entities": be.entities,
                "attributes": be.attributes,
            }
        else:
            first_line = (
                mb["text"][:80].split("\n")[0] if mb["text"] else "Untitled block"
            )
            block = {
                "type": mb["preliminary_type"],
                "label": first_line,
                "text": mb["text"],
                "html": mb["html"],
                "box_2d": mb["box_2d"],
                "visibility": "dm_only",
                "entities": [],
                "attributes": {},
            }
        merged.append(block)

    return merged


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EXTRACT + VALIDATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def extract_and_validate(
    marker_blocks: list[dict],
    page_number: int,
    enrichment_model: str = ENRICHMENT_MODEL,
    max_retries: int = 2,
) -> tuple[PageExtraction | None, list[dict], list[str]]:
    """
    Enrich pre-extracted Marker blocks and validate.
    Returns (validated, raw_blocks, errors).
    """
    errors_log: list[str] = []

    enrichment = enrich_page_blocks(
        marker_blocks,
        page_number,
        model=enrichment_model,
        max_retries=max_retries,
    )

    merged = merge_marker_and_enrichment(marker_blocks, enrichment)

    try:
        validated = PageExtraction(blocks=merged)
        return validated, merged, []
    except Exception as e:
        errors_log.append(f"Validation error: {e}")
        return None, merged, errors_log


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ANNOTATED IMAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BLOCK_COLORS: dict[str, tuple[int, int, int]] = {
    "chapter_heading": (192, 57, 43),
    "section_heading": (46, 134, 193),
    "subsection_heading": (26, 119, 66),
    "body_text": (140, 130, 115),
    "read_aloud": (183, 149, 11),
    "stat_block": (125, 60, 152),
    "lore_sidebar": (20, 143, 119),
    "dm_guidance": (52, 73, 94),
    "spell_description": (202, 111, 30),
    "item_description": (136, 78, 160),
    "class_feature": (40, 116, 166),
    "race_trait": (23, 165, 137),
    "feat_description": (211, 84, 0),
    "rule_callout": (241, 196, 15),
    "table": (22, 160, 133),
    "map": (100, 100, 100),
    "illustration": (100, 100, 100),
    "handout": (149, 165, 166),
    "page_footer": (160, 160, 160),
    "blank_page": (200, 200, 200),
}


def draw_annotations(image_path: Path, blocks: list[dict], output_path: Path):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path)
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11
        )
    except (OSError, IOError):
        font = ImageFont.load_default()

    for block in blocks:
        box = block.get("box_2d", [0, 0, 0, 0])
        btype = block.get("type", "body_text")
        color = BLOCK_COLORS.get(btype, (128, 128, 128))

        y0 = int(box[0] / 1000 * h)
        x0 = int(box[1] / 1000 * w)
        y1 = int(box[2] / 1000 * h)
        x1 = int(box[3] / 1000 * w)

        draw.rectangle(
            [x0, y0, x1, y1], fill=(*color, 30), outline=(*color, 200), width=2
        )

        tag = f"{btype}: {block.get('label', '')}"[:60]
        bbox = draw.textbbox((x0, y0 - 14), tag, font=font)
        draw.rectangle(
            [bbox[0] - 1, bbox[1] - 1, bbox[2] + 3, bbox[3] + 1],
            fill=(*color, 220),
        )
        draw.text((x0, y0 - 14), tag, fill=(255, 255, 255), font=font)

    img.save(output_path)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HIERARCHY TREE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def print_tree(blocks: list[dict]):
    for b in blocks:
        btype = b.get("type", "body_text")
        try:
            depth = get_depth(BlockType(btype))
        except ValueError:
            depth = 3
        indent = "  " * depth
        label = b.get("label", "")
        preview = b.get("text", "")[:70].replace("\n", " ")
        typer.echo(f"{indent}[{btype.upper()}] {label}", err=True)
        if preview and btype not in ("map", "illustration"):
            typer.echo(f"{indent}  {preview}...", err=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EVALUATION PAYLOAD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def build_evaluation_payload(
    image_path: Path,
    blocks: list[dict],
    spec_path: Optional[Path] = None,
) -> dict:
    spec_text = ""
    if spec_path and spec_path.exists():
        spec_text = spec_path.read_text()
    else:
        spec_text = (
            "See the PROMPT section — the enrichment system prompt IS the spec. "
            "Evaluate the OUTPUT against the rules defined in the prompt."
        )

    return {
        "prompt": ENRICHMENT_SYSTEM_PROMPT,
        "input": f"[Page image: {image_path.name}]",
        "output": blocks,
        "spec": spec_text,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RENDER HELPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def render_page_to_png(pdf_path: Path, page_number: int, dpi: int = 200) -> Path:
    """Render a single PDF page to PNG. page_number is 1-indexed."""
    import fitz  # gazelle:ignore fitz

    doc = fitz.open(str(pdf_path))
    page = doc[page_number - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    tmp = Path(tempfile.mktemp(suffix=".png", prefix="tomeslicer_page_"))
    pix.save(str(tmp))
    doc.close()
    return tmp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLI COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.command()
def extract_page(
    pdf: Path = typer.Argument(..., help="PDF file"),
    page: int = typer.Option(..., "--page", "-p", help="Page number (1-indexed)"),
    output: Optional[Path] = typer.Option(None, "-o", help="Output JSON path"),
    no_annotate: bool = typer.Option(False, help="Skip annotated image"),
    max_retries: int = typer.Option(2, help="Enrichment retry attempts"),
    enrichment_model: str = typer.Option(
        ENRICHMENT_MODEL, "--model", help="Enrichment model"
    ),
):
    """Extract blocks from a single PDF page."""
    typer.echo(
        f"Extracting page {page} from {pdf.name} via Marker + {enrichment_model}...",
        err=True,
    )

    # Stage 1: Marker extraction
    typer.echo("  Stage 1: Marker OCR/layout...", err=True)
    pages = extract_with_marker(pdf, page_range=[page - 1])
    if not pages or not pages[0]["blocks"]:
        typer.echo("✗ Marker extracted no blocks", err=True)
        raise typer.Exit(1)

    marker_blocks = pages[0]["blocks"]
    typer.echo(f"  Marker found {len(marker_blocks)} blocks", err=True)

    # Stage 2: Enrichment + validation
    typer.echo("  Stage 2: Gemini enrichment...", err=True)
    validated, raw_blocks, errors = extract_and_validate(
        marker_blocks,
        page,
        enrichment_model=enrichment_model,
        max_retries=max_retries,
    )

    if validated:
        blocks = [b.model_dump() for b in validated.blocks]
        typer.echo(f"✓ {len(blocks)} blocks extracted and validated", err=True)
    elif raw_blocks:
        blocks = raw_blocks
        typer.echo(f"⚠ {len(blocks)} blocks but validation failed:", err=True)
        for e in errors:
            typer.echo(f"  {e}", err=True)
    else:
        typer.echo("✗ Extraction failed", err=True)
        for e in errors:
            typer.echo(f"  {e}", err=True)
        raise typer.Exit(1)

    print_tree(blocks)

    # Render page to PNG for annotation
    if not no_annotate:
        page_png = render_page_to_png(pdf, page)
        try:
            ann_name = f"page-{page:03d}_annotated.png"
            ann_path = (output.parent / ann_name) if output else Path(ann_name)
            draw_annotations(page_png, blocks, ann_path)
            typer.echo(f"Annotated -> {ann_path}", err=True)
        finally:
            page_png.unlink(missing_ok=True)

    out = json.dumps(blocks, indent=2, ensure_ascii=False)
    if output:
        output.write_text(out)
        typer.echo(f"JSON -> {output}", err=True)
    else:
        print(out)


@app.command()
def extract_pdf(
    pdf: Path = typer.Argument(..., help="Input PDF file"),
    output_dir: Path = typer.Option("output", help="Output directory"),
    concurrency: int = typer.Option(5, help="Parallel enrichment sessions"),
    limit: Optional[int] = typer.Option(None, help="Limit to first N pages"),
    max_retries: int = typer.Option(2, help="Retries per page"),
    enrichment_model: str = typer.Option(
        ENRICHMENT_MODEL, "--model", help="Enrichment model"
    ),
):
    """Extract all pages from a PDF."""
    output_dir.mkdir(exist_ok=True)

    # Stage 1: Marker batch extraction
    page_range = list(range(limit)) if limit else None
    typer.echo(f"Stage 1: Marker OCR/layout for {pdf.name}...", err=True)
    pages = extract_with_marker(pdf, page_range=page_range)
    total_blocks = sum(len(p["blocks"]) for p in pages)
    typer.echo(
        f"  Marker extracted {total_blocks} blocks across {len(pages)} pages",
        err=True,
    )

    # Stage 2: Parallel enrichment
    typer.echo(
        f"Stage 2: Enriching {len(pages)} pages (concurrency={concurrency})",
        err=True,
    )

    stats = {"ok": 0, "warn": 0, "failed": 0, "skipped": 0}

    def process_one(page_data: dict) -> dict:
        page_num = page_data["page_number"]
        out_file = output_dir / f"page-{page_num:03d}.json"
        if out_file.exists():
            return {"page": f"page-{page_num:03d}", "status": "skipped"}

        validated, raw_blocks, errs = extract_and_validate(
            page_data["blocks"],
            page_num,
            enrichment_model=enrichment_model,
            max_retries=max_retries,
        )

        if validated:
            blocks = [b.model_dump() for b in validated.blocks]
        elif raw_blocks:
            blocks = raw_blocks
            (output_dir / f"page-{page_num:03d}.warnings.txt").write_text(
                "\n".join(errs)
            )
        else:
            (output_dir / f"page-{page_num:03d}.error.txt").write_text("\n".join(errs))
            return {"page": f"page-{page_num:03d}", "status": "failed"}

        out_file.write_text(json.dumps(blocks, indent=2, ensure_ascii=False))
        status = "ok" if validated else "warn"
        return {
            "page": f"page-{page_num:03d}",
            "status": status,
            "blocks": len(blocks),
        }

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(process_one, p): p for p in pages}
            for future in as_completed(futures):
                result = future.result()
                status = result["status"]
                stats[status] = stats.get(status, 0) + 1
                icon = {"ok": "✓", "warn": "⚠", "failed": "✗", "skipped": "·"}[status]
                extra = (
                    f" ({result.get('blocks', '')} blocks)"
                    if "blocks" in result
                    else ""
                )
                typer.echo(f"  {icon} {result['page']}{extra}")
    except KeyboardInterrupt:
        typer.echo("\n\nInterrupted! Cancelling pending pages...", err=True)
        for f in futures:
            f.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        typer.echo(f"Partial stats: {stats}", err=True)

    typer.echo(f"\nDone: {stats}")

    # Merge
    all_blocks = []
    for f in sorted(output_dir.glob("page-*.json")):
        page_blocks = json.loads(f.read_text())
        for b in page_blocks:
            b["_source_page"] = f.stem
        all_blocks.extend(page_blocks)

    merged = output_dir / "_merged.json"
    merged.write_text(json.dumps(all_blocks, indent=2, ensure_ascii=False))
    typer.echo(f"Merged {len(all_blocks)} blocks -> {merged}")


@app.command()
def evaluate(
    image: Path = typer.Argument(..., help="Page image"),
    extraction: Path = typer.Argument(..., help="Extraction JSON"),
    spec: Optional[Path] = typer.Option(None, help="Extraction spec markdown"),
    output: Optional[Path] = typer.Option(None, "-o", help="Save evaluation payload"),
):
    """Build evaluation payload for the prompt refiner."""
    blocks = json.loads(extraction.read_text())
    payload = build_evaluation_payload(image, blocks, spec)

    out = json.dumps(payload, indent=2, ensure_ascii=False)
    if output:
        output.write_text(out)
        typer.echo(f"Evaluation payload -> {output}")
    else:
        print(out)

    typer.echo(
        "\nFeed this + page image into Claude with tomeslicer-prompt-refiner.md",
        err=True,
    )


@app.command()
def annotate(
    image: Path = typer.Argument(..., help="Page image"),
    extraction: Path = typer.Argument(..., help="Extraction JSON"),
    output: Optional[Path] = typer.Option(None, "-o", help="Output image path"),
):
    """Overlay bounding boxes on a page image."""
    blocks = json.loads(extraction.read_text())
    out_path = output or image.with_stem(f"{image.stem}_annotated").with_suffix(".png")
    draw_annotations(image, blocks, out_path)
    typer.echo(f"Annotated -> {out_path}")


@app.command()
def show_prompt():
    """Print the current enrichment system prompt."""
    print(ENRICHMENT_SYSTEM_PROMPT)


@app.command()
def validate(
    extraction: Path = typer.Argument(..., help="Extraction JSON to validate"),
):
    """Validate an extraction JSON against the schema."""
    blocks = json.loads(extraction.read_text())
    try:
        validated = PageExtraction(blocks=blocks)
        typer.echo(f"✓ Valid — {len(validated.blocks)} blocks")
        print_tree(blocks)
    except Exception as e:
        typer.echo(f"✗ Invalid:\n{e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
