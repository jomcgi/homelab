# gazelle:python_generation_mode none

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load(":multitool_tar.bzl", "multitool_tar")
load(":node_tar.bzl", "node_tar")
load(":python_tar.bzl", "python_tar")

multitool_tar(
    name = "tools_tar",
    tools = [
        "argocd",
        "buildozer",
        "crane",
        "gazelle",
        "gh",
        "gofumpt",
        "helm",
        "kind",
        "op",
        "ruff",
        "shfmt",
    ],
)

# Per-platform Node.js binary tars.
# Creates :node_tar_linux_amd64, :node_tar_linux_arm64, :node_tar_darwin_arm64
# each containing /usr/bin/node for the target platform.
node_tar(name = "node_tar")

# Package pnpm from the aspect_rules_js-managed @pnpm repo.
# pnpm is a JS script (cross-platform) that runs on Node.js.
# Places the package at /usr/local/lib/node_modules/pnpm/
# with a symlink at /usr/bin/pnpm for PATH discovery.
genrule(
    name = "pnpm_tar",
    srcs = ["@pnpm//:pkg"],
    outs = ["pnpm.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib/node_modules/pnpm"
        mkdir -p "$$DEST"
        SRC_DIR=$$(echo '$(location @pnpm//:pkg)' | tr ' ' '\\n' | head -1)
        cp -rL "$$SRC_DIR/." "$$DEST/"
        chmod 755 "$$DEST/bin/pnpm.cjs"
        mkdir -p "$$WORK/usr/bin"
        ln -s "../local/lib/node_modules/pnpm/bin/pnpm.cjs" "$$WORK/usr/bin/pnpm"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    """,
)

# Package prettier from the pnpm lockfile-managed npm package.
# Places the package at /usr/local/lib/node_modules/prettier/
# with a symlink at /usr/bin/prettier for PATH discovery.
genrule(
    name = "prettier_tar",
    srcs = ["//:node_modules/prettier"],
    outs = ["prettier.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib/node_modules/prettier"
        mkdir -p "$$DEST"
        SRC_DIR=$$(echo '$(locations //:node_modules/prettier)' | tr ' ' '\\n' | grep 'prettier$$' | head -1)
        cp -rL "$$SRC_DIR/." "$$DEST/"
        chmod 755 "$$DEST/bin/prettier.cjs"
        mkdir -p "$$WORK/usr/bin"
        ln -s "../local/lib/node_modules/prettier/bin/prettier.cjs" "$$WORK/usr/bin/prettier"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    """,
)

# Shim py_venv_binary that declares all monorepo pip deps.
# The binary itself does nothing — it exists solely so py_image_layer can
# package its transitive dependency tree (interpreter + stdlib + pip packages).
# Platform-conditional packages (e.g. pyobjc on macOS, dbus_fast on Linux)
# are handled by rules_python's platform-aware wheel resolution.
py_venv_binary(
    name = "python_deps",
    srcs = ["python_deps.py"],
    main = "python_deps.py",
    deps = [
        # All pip packages from requirements/all.txt (excluding Windows-only).
        # Platform-conditional packages (pyobjc for macOS, dbus_fast for Linux,
        # etc.) are handled by rules_python's platform-aware wheel resolution.
        # Packages requiring native system libraries (GDAL, OpenCV, osmium) are
        # excluded since they need libraries not present in the base image.
        "@pip//affine",
        "@pip//aiofile",
        "@pip//aiohappyeyeballs",
        "@pip//aiohttp",
        "@pip//aiosignal",
        "@pip//aiosqlite",
        "@pip//annotated_types",
        "@pip//anyio",
        "@pip//apscheduler",
        "@pip//asgiref",
        "@pip//astral",
        "@pip//asyncstdlib",
        "@pip//attrs",
        "@pip//authlib",
        "@pip//babel",
        "@pip//beartype",
        "@pip//beautifulsoup4",
        "@pip//bng_latlon",
        "@pip//boltons",
        "@pip//boto3",
        "@pip//botocore",
        "@pip//bracex",
        "@pip//brotli",
        "@pip//cachetools",
        "@pip//caio",
        "@pip//cattrs",
        "@pip//certifi",
        "@pip//cffi",
        "@pip//charset_normalizer",
        "@pip//click",
        "@pip//click_default_group",
        "@pip//click_option_group",
        "@pip//cligj",
        "@pip//colorama",
        "@pip//construct",
        "@pip//constructs",
        "@pip//copier",
        "@pip//courlan",
        "@pip//cryptography",
        "@pip//cyclopts",
        "@pip//dateparser",
        "@pip//dbus_fast",
        "@pip//defusedxml",
        "@pip//distro",
        "@pip//dnspython",
        "@pip//docstring_parser",
        "@pip//docutils",
        "@pip//dunamai",
        "@pip//email_validator",
        "@pip//exceptiongroup",
        "@pip//face",
        "@pip//fastapi",
        "@pip//fastmcp",
        "@pip//feedparser",
        "@pip//frozenlist",
        "@pip//funcy",
        "@pip//glom",
        "@pip//google_auth",
        "@pip//google_genai",
        "@pip//googleapis_common_protos",
        "@pip//grpcio",
        "@pip//h11",
        "@pip//haversine",
        "@pip//htmldate",
        "@pip//httpcore",
        "@pip//httptools",
        "@pip//httpx",
        "@pip//httpx_sse",
        "@pip//idna",
        "@pip//ifaddr",
        "@pip//importlib_metadata",
        "@pip//importlib_resources",
        "@pip//iniconfig",
        "@pip//jaraco_classes",
        "@pip//jaraco_context",
        "@pip//jaraco_functools",
        "@pip//jeepney",
        "@pip//jinja2",
        "@pip//jinja2_ansible_filters",
        "@pip//jmespath",
        "@pip//jsii",
        "@pip//jsonref",
        "@pip//jsonschema",
        "@pip//jsonschema_path",
        "@pip//jsonschema_specifications",
        "@pip//justext",
        "@pip//keyring",
        "@pip//lxml",
        "@pip//lxml_html_clean",
        "@pip//mako",
        "@pip//markdown_it_py",
        "@pip//markupsafe",
        "@pip//mcp",
        "@pip//mdurl",
        "@pip//more_itertools",
        "@pip//multidict",
        "@pip//mypy",
        "@pip//mypy_extensions",
        "@pip//nats_py",
        "@pip//networkx",
        "@pip//numpy",
        "@pip//openapi_pydantic",
        "@pip//opentelemetry_api",
        "@pip//opentelemetry_exporter_otlp",
        "@pip//opentelemetry_exporter_otlp_proto_common",
        "@pip//opentelemetry_exporter_otlp_proto_grpc",
        "@pip//opentelemetry_exporter_otlp_proto_http",
        "@pip//opentelemetry_instrumentation",
        "@pip//opentelemetry_instrumentation_asgi",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//opentelemetry_instrumentation_httpx",
        "@pip//opentelemetry_instrumentation_requests",
        "@pip//opentelemetry_instrumentation_threading",
        "@pip//opentelemetry_proto",
        "@pip//opentelemetry_sdk",
        "@pip//opentelemetry_semantic_conventions",
        "@pip//opentelemetry_util_http",
        "@pip//packaging",
        "@pip//pandas",
        "@pip//parse",
        "@pip//parse_type",
        "@pip//pathable",
        "@pip//pathspec",
        "@pip//peewee",
        "@pip//pexpect",
        "@pip//pillow",
        "@pip//platformdirs",
        "@pip//pluggy",
        "@pip//plumbum",
        "@pip//prompt_toolkit",
        "@pip//propcache",
        "@pip//protobuf",
        "@pip//ptyprocess",
        "@pip//publication",
        "@pip//py_key_value_aio",
        "@pip//pyasn1",
        "@pip//pyasn1_modules",
        "@pip//pycparser",
        "@pip//pydantic",
        "@pip//pydantic_core",
        "@pip//pydantic_extra_types",
        "@pip//pydantic_settings",
        "@pip//pydantic_sqlite",
        "@pip//pygments",
        "@pip//pyjwt",
        "@pip//pyparsing",
        "@pip//pyperclip",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//pytest_bdd",
        "@pip//python_dateutil",
        "@pip//python_dotenv",
        "@pip//python_multipart",
        "@pip//pytz",
        "@pip//pyyaml",
        "@pip//questionary",
        "@pip//referencing",
        "@pip//regex",
        "@pip//requests",
        "@pip//requests_cache",
        "@pip//returns",
        "@pip//rich",
        "@pip//rich_rst",
        "@pip//rpds_py",
        "@pip//rsa",
        "@pip//ruamel_yaml",
        "@pip//ruamel_yaml_clib",
        "@pip//s3transfer",
        "@pip//secretstorage",
        "@pip//semantic_version",
        "@pip//sgmllib3k",
        "@pip//shapely",
        "@pip//shellingham",
        "@pip//six",
        "@pip//sniffio",
        "@pip//soupsieve",
        "@pip//sqlite_fts4",
        "@pip//sqlite_utils",
        "@pip//sse_starlette",
        "@pip//starlette",
        "@pip//sunrisesunset",
        "@pip//tabulate",
        "@pip//tenacity",
        "@pip//timelength",
        "@pip//tinydb",
        "@pip//tld",
        "@pip//tomli",
        "@pip//trafilatura",
        "@pip//typeguard",
        "@pip//typer",
        "@pip//typing_extensions",
        "@pip//typing_inspection",
        "@pip//tzlocal",
        "@pip//url_normalize",
        "@pip//urllib3",
        "@pip//uvicorn",
        "@pip//uvloop",
        "@pip//watchfiles",
        "@pip//wcmatch",
        "@pip//wcwidth",
        "@pip//websockets",
        "@pip//wrapt",
        "@pip//yarl",
        "@pip//zeroconf",
        "@pip//zipp",
    ],
)

# Per-platform Python runtime + pip deps tars.
# Creates :python_tar_linux_amd64, :python_tar_linux_arm64, :python_tar_darwin_arm64
# each containing py_image_layer tars (interpreter + stdlib + pip packages)
# for the target platform.
#
# NOTE: darwin_arm64 is experimental — py_image_layer was designed for Linux
# OCI container images and may not produce valid tars for macOS. If the
# darwin variant fails to build, the Linux variants are still usable.
python_tar(
    name = "python_tar",
    binary = ":python_deps",
)

oci_image(
    name = "image_linux_amd64",
    architecture = "amd64",
    os = "linux",
    tars = [
        ":tools_tar_linux_amd64",
        ":node_tar_linux_amd64",
        ":python_tar_linux_amd64",
        ":pnpm_tar",
        ":prettier_tar",
    ],
)

oci_image(
    name = "image_linux_arm64",
    architecture = "arm64",
    os = "linux",
    tars = [
        ":tools_tar_linux_arm64",
        ":node_tar_linux_arm64",
        ":python_tar_linux_arm64",
        ":pnpm_tar",
        ":prettier_tar",
    ],
)

oci_image(
    name = "image_darwin_arm64",
    architecture = "arm64",
    os = "darwin",
    tars = [
        ":tools_tar_darwin_arm64",
        ":node_tar_darwin_arm64",
        ":python_tar_darwin_arm64",
        ":pnpm_tar",
        ":prettier_tar",
    ],
)

oci_image_index(
    name = "image",
    images = [
        ":image_linux_amd64",
        ":image_linux_arm64",
        ":image_darwin_arm64",
    ],
)

# Stamped tags for CI (branch + timestamp)
expand_template(
    name = "image_stamped_tags_ci",
    out = "image_stamped_ci.tags.txt",
    stamp_substitutions = {
        "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
    template = ["{STABLE_BRANCH_TAG}", "{STABLE_IMAGE_TAG}"],
)

# Stamped tags for local builds (timestamp only)
expand_template(
    name = "image_stamped_tags_local",
    out = "image_stamped_local.tags.txt",
    stamp_substitutions = {
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
    template = ["{STABLE_IMAGE_TAG}"],
)

oci_push(
    name = "image.push",
    image = ":image",
    remote_tags = select({
        "//tools/oci:ci_build": "image_stamped_tags_ci",
        "//conditions:default": "image_stamped_tags_local",
    }),
    repository = "ghcr.io/jomcgi/homelab-tools",
    visibility = ["//images:__pkg__"],
)
