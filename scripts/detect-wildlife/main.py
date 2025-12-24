import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from open_gopro import WiredGoPro
from open_gopro.models import constants, proto

# Monkey-patch: SDK hardcodes port 8080, but Hero 13 firmware uses port 80
# See: https://github.com/gopro/OpenGoPro/issues/XXX (port mismatch)
WiredGoPro._BASE_ENDPOINT = "http://{ip}:80/"

# Output directory
OUTPUT_DIR = Path(__file__).parent / "tmp"

app = typer.Typer(help="GoPro wildlife detection camera control")


async def configure_gopro(
    gopro: WiredGoPro,
    *,
    raw: bool = True,
    gps: bool = True,
) -> None:
    """Configure camera for high-resolution photo capture."""
    # Set PRO mode (required for full resolution control)
    await gopro.http_setting.control_mode.set(constants.settings.ControlMode.PRO)

    # Load photo preset group
    await gopro.http_command.load_preset_group(
        group=proto.EnumPresetGroup.PRESET_GROUP_ID_PHOTO
    )

    # Set high-resolution lens (27MP wide - required for RAW)
    lens_options = [
        constants.settings.PhotoLens.WIDE_27_MP,
        constants.settings.PhotoLens.WIDE_23_MP,
        constants.settings.PhotoLens.WIDE_12_MP,
    ]
    for lens in lens_options:
        if (await gopro.http_setting.photo_lens.set(lens)).ok:
            break

    # RAW mode
    if raw:
        result = await gopro.http_setting.photo_output.set(
            constants.settings.PhotoOutput.RAW
        )
        if result.ok:
            print("RAW mode enabled")
        else:
            print("Warning: Could not enable RAW mode")
    else:
        await gopro.http_setting.photo_output.set(
            constants.settings.PhotoOutput.STANDARD
        )

    # Disable photo interval (single shot)
    await gopro.http_setting.photo_single_interval.set(
        constants.settings.PhotoSingleInterval.OFF
    )

    # GPS
    if gps:
        result = await gopro.http_setting.gps.set(constants.settings.Gps.ON)
        if result.ok:
            print("GPS enabled")
        else:
            print("Warning: Could not enable GPS")


async def capture_photo(
    gopro: WiredGoPro, output_dir: Path
) -> tuple[Path, Path | None, dict]:
    """Capture a single photo and download it. Returns (jpg_path, gpr_path, timing_info)."""
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timing = {}

    # Get media list before capture
    t0 = time.perf_counter()
    media_before = set((await gopro.http_command.get_media_list()).data.files)

    # Take photo (with retry if camera is busy)
    t1 = time.perf_counter()
    for attempt in range(3):
        try:
            await gopro.http_command.set_shutter(shutter=constants.Toggle.ENABLE)
            break
        except Exception as e:
            if attempt < 2:
                print(f"  Shutter busy, retrying in 2s... ({e})")
                await asyncio.sleep(2)
            else:
                raise
    t2 = time.perf_counter()
    timing["capture"] = t2 - t1

    # Small delay to let camera finish writing
    await asyncio.sleep(0.5)

    # Get media list after capture
    media_after = set((await gopro.http_command.get_media_list()).data.files)

    # Find the new photo
    new_photos = media_after.difference(media_before)
    if not new_photos:
        raise RuntimeError("No new photo captured")

    photo = new_photos.pop()

    # Download the JPG
    jpg_path = output_dir / f"{timestamp}.jpg"
    t3 = time.perf_counter()
    await gopro.http_command.download_file(
        camera_file=photo.filename, local_file=str(jpg_path)
    )
    t4 = time.perf_counter()
    timing["jpg_download"] = t4 - t3

    # Check if RAW file exists and download it
    gpr_path = None
    if photo.raw == "1":
        gpr_filename = photo.filename.replace(".JPG", ".GPR")
        gpr_path = output_dir / f"{timestamp}.gpr"
        t5 = time.perf_counter()
        await gopro.http_command.download_file(
            camera_file=gpr_filename, local_file=str(gpr_path)
        )
        t6 = time.perf_counter()
        timing["gpr_download"] = t6 - t5

    timing["total"] = time.perf_counter() - t0

    return jpg_path, gpr_path, timing


async def _main(
    capture: bool,
    raw: bool,
    gps: bool,
    output_dir: Path,
    loop: bool,
    interval: int,
    count: int | None,
) -> None:
    # Retry connection with longer timeout for camera wakeup
    gopro = WiredGoPro()
    for attempt in range(5):
        try:
            print(f"Connecting to camera (attempt {attempt + 1}/5)...")
            await gopro.open(timeout=15, retries=3)
            break
        except Exception as e:
            if attempt < 4:
                print(f"Connection failed: {e}")
                print("Waiting 5s for camera to wake up...")
                await asyncio.sleep(5)
            else:
                print("Failed to connect after 5 attempts.")
                print("Try: unplug USB, wait 5s, plug back in (triggers WAKE=2)")
                raise

    try:
        print("Configuring camera...")
        await configure_gopro(gopro, raw=raw, gps=gps)
        print("Configuration complete\n")

        if not capture:
            print("Skipping capture (--no-capture)")
            return

        captured = 0
        errors = 0
        all_timings: list[dict] = []
        session_start = time.perf_counter()

        while True:
            try:
                captured += 1
                if count:
                    print(f"\n[{captured}/{count}] Capturing...")
                else:
                    print(f"\n[{captured}] Capturing...")

                jpg_path, gpr_path, timing = await capture_photo(gopro, output_dir)
                all_timings.append(timing)

                jpg_size = os.path.getsize(jpg_path) / 1024 / 1024
                print(f"Saved: {jpg_path} ({jpg_size:.1f}MB)")

                if gpr_path:
                    gpr_size = os.path.getsize(gpr_path) / 1024 / 1024
                    print(f"Saved: {gpr_path} ({gpr_size:.1f}MB)")

                # Show timing for this capture
                timing_parts = [
                    f"capture={timing['capture']:.1f}s",
                    f"jpg={timing['jpg_download']:.1f}s",
                ]
                if "gpr_download" in timing:
                    timing_parts.append(f"raw={timing['gpr_download']:.1f}s")
                timing_parts.append(f"total={timing['total']:.1f}s")
                print(f"Timing: {', '.join(timing_parts)}")

                # Show running stats
                if len(all_timings) > 1:
                    avg_total = sum(t["total"] for t in all_timings) / len(all_timings)
                    elapsed = time.perf_counter() - session_start
                    rate = len(all_timings) / (elapsed / 60)  # photos per minute
                    print(f"Stats: avg={avg_total:.1f}s/photo, rate={rate:.1f}/min")

                errors = 0  # Reset error count on success

            except Exception as e:
                errors += 1
                print(f"Error: {e}")
                if errors >= 3:
                    print("Too many consecutive errors, stopping")
                    break

            # Check if we should stop
            if not loop:
                break
            if count and captured >= count:
                print(f"\nCompleted {count} captures")
                break

            # Wait for next capture (minimum 2s to let camera recover)
            wait_time = max(interval, 2)
            if wait_time > 2:
                print(f"Waiting {wait_time}s until next capture...")
            await asyncio.sleep(wait_time)

        # Final summary
        if all_timings:
            elapsed = time.perf_counter() - session_start
            avg_total = sum(t["total"] for t in all_timings) / len(all_timings)
            avg_capture = sum(t["capture"] for t in all_timings) / len(all_timings)
            avg_jpg = sum(t["jpg_download"] for t in all_timings) / len(all_timings)
            print(f"\n{'=' * 50}")
            print(f"Session complete: {len(all_timings)} photos in {elapsed:.1f}s")
            print(
                f"Average: {avg_total:.1f}s total (capture={avg_capture:.1f}s, jpg={avg_jpg:.1f}s)"
            )
            if any("gpr_download" in t for t in all_timings):
                gpr_times = [
                    t["gpr_download"] for t in all_timings if "gpr_download" in t
                ]
                print(f"         raw={sum(gpr_times) / len(gpr_times):.1f}s")
            print(f"Max rate: {60 / avg_total:.1f} photos/min (without interval delay)")
    finally:
        await gopro.close()


@app.command()
def main(
    capture: Annotated[bool, typer.Option(help="Capture a photo")] = True,
    raw: Annotated[bool, typer.Option(help="Enable RAW (GPR) output")] = True,
    gps: Annotated[bool, typer.Option(help="Enable GPS location tagging")] = True,
    output_dir: Annotated[
        Path, typer.Option(help="Output directory for photos")
    ] = OUTPUT_DIR,
    loop: Annotated[bool, typer.Option(help="Run continuously in a loop")] = False,
    interval: Annotated[
        int, typer.Option(help="Seconds between captures (when looping)")
    ] = 30,
    count: Annotated[
        int | None, typer.Option(help="Number of photos to capture (None=unlimited)")
    ] = None,
) -> None:
    """Capture high-resolution photos from GoPro for wildlife detection."""
    asyncio.run(
        _main(
            capture=capture,
            raw=raw,
            gps=gps,
            output_dir=output_dir,
            loop=loop,
            interval=interval,
            count=count,
        )
    )


if __name__ == "__main__":
    app()
