#!/usr/bin/env python3
"""
Check status of Wikidata dump and download when ready.

Usage:
    python3 check_wikidata_dump.py --dump-id 5175 [--download] [--output dump.json.gz]
"""

import requests
import sys
import argparse
import os
from pathlib import Path


def check_dump_status(dump_id: str):
    """Check status of Wikidata dump."""

    url = f"https://wdumps.toolforge.org/api/dumps/{dump_id}"

    print(f"Checking dump {dump_id}...")
    print(f"URL: https://wdumps.toolforge.org/dump/{dump_id}")
    print()

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Extract status information
        status = data.get('status', 'unknown')
        entity_count = data.get('entity_count', 0)
        compressed_size = data.get('compressed_size', 0)
        zenodo_link = data.get('zenodo_link')
        download_link = data.get('download_link')

        print("="*60)
        print("WIKIDATA DUMP STATUS")
        print("="*60)
        print(f"Dump ID: {dump_id}")
        print(f"Status: {status}")
        print(f"Entities: {entity_count:,}")

        # Convert bytes to MB/GB
        if compressed_size > 0:
            if compressed_size > 1_000_000_000:
                size_str = f"{compressed_size / 1_000_000_000:.2f} GB"
            else:
                size_str = f"{compressed_size / 1_000_000:.2f} MB"
            print(f"Compressed Size: {size_str}")
        else:
            print(f"Compressed Size: 0 bytes (not generated)")

        print()

        if status == 'completed' or zenodo_link or download_link:
            print("✓ DUMP IS READY FOR DOWNLOAD")

            if zenodo_link:
                print(f"\nZenodo Link: {zenodo_link}")
            if download_link:
                print(f"Download Link: {download_link}")

            return download_link or zenodo_link

        elif status == 'processing':
            print("⏳ Dump is currently being generated...")
            print("   Check back later.")
            return None

        elif status == 'failed':
            print("✗ Dump generation FAILED")
            return None

        else:
            print(f"⏳ Dump not yet started or in queue...")
            print("   Check back later.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error checking dump status: {e}")
        return None


def download_dump(url: str, output_file: str):
    """Download dump file."""

    print(f"\nDownloading to {output_file}...")

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        # Download with progress
        with open(output_file, 'wb') as f:
            downloaded = 0
            chunk_size = 8192

            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    # Print progress every 100 MB
                    if downloaded % (100 * 1024 * 1024) < chunk_size:
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"  Downloaded: {downloaded / 1_000_000:.1f} MB ({percent:.1f}%)")
                        else:
                            print(f"  Downloaded: {downloaded / 1_000_000:.1f} MB")

        print(f"\n✓ Download complete: {output_file}")
        print(f"  Size: {os.path.getsize(output_file) / 1_000_000:.1f} MB")

    except Exception as e:
        print(f"\n✗ Download failed: {e}")
        # Clean up partial download
        if os.path.exists(output_file):
            os.remove(output_file)


def main():
    """Main execution."""

    parser = argparse.ArgumentParser(
        description='Check Wikidata dump status and optionally download'
    )
    parser.add_argument('--dump-id', required=True, help='Wikidata dump ID (e.g., 5175)')
    parser.add_argument('--download', action='store_true', help='Download dump if ready')
    parser.add_argument('--output', default='wikidata_dump.json.gz', help='Output file path')

    args = parser.parse_args()

    download_link = check_dump_status(args.dump_id)

    if download_link and args.download:
        download_dump(download_link, args.output)
        print("\nNext step:")
        print(f"  python3 parse_wikidata_dump.py {args.output} wikidata_global_complete.json.gz")
    elif download_link:
        print("\nTo download:")
        print(f"  python3 check_wikidata_dump.py --dump-id {args.dump_id} --download --output {args.output}")


if __name__ == '__main__':
    main()
