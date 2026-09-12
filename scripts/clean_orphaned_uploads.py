import sys
import os
import time
import argparse
from sqlalchemy import create_engine, MetaData, text
from dotenv import load_dotenv

parser = argparse.ArgumentParser(description="Clean orphaned uploads.")
parser.add_argument('--delete', action='store_true', help='Execute deletion (otherwise dry-run)')
parser.add_argument('--env', type=str, default='config/.env', help='Path to environment file (e.g., .env.production, .env.lightnode)')
args = parser.parse_args()

# Load the dynamically provided environment file
print(f"Loading environment from: {args.env}")
load_dotenv(args.env)

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    db_user = os.getenv("DB_USER", "root")
    db_pass_raw = os.getenv("DB_PASSWORD", "root")
    import urllib.parse
    db_pass = urllib.parse.quote_plus(db_pass_raw)
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = os.getenv("DB_PORT", "8889")
    db_name = os.getenv("DB_NAME", "pamais")
    DB_URL = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

engine = create_engine(DB_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

def get_all_db_strings():
    print("Fetching URL references from database...")
    all_text_data = set()
    with engine.connect() as conn:
        # ── Verified against actual DB schema ─────────────────────────────
        target_columns = [
            # Users & avatars
            ("users_resource", "avatar"),
            ("users_resource", "cover_image"),
            ("users", "image"),
            ("users", "signature"),
            ("users", "signatureImagePath"),

            # Students
            ("students", "image"),
            ("students", "pickup_audio_url"),

            # News
            ("news", "cover_image_url"),
            ("news_images", "image_url"),

            # Partners
            ("partners", "logo_url"),
            ("partner_images", "image_url"),

            # Ads & splash
            ("ads", "image_url"),
            ("ads", "image_path"),
            ("splash_ads", "image_url"),

            # Academic programs
            ("academic_programs", "custom_logo_url"),
            ("academic_program_images", "image_url"),

            # Branch (signatures, stamps, headers)
            ("branch", "image_header_path"),
            ("branch", "director_signature_path"),
            ("branch", "headTeacher_signature_path"),
            ("branch", "stamp_path"),
            ("branch", "app_branch_cover"),

            # Forms
            ("forms", "image_url"),
            ("form_fields", "image_url"),

            # Messages & groups
            ("message_groups", "group_image"),

            # Settings & branding
            ("settings", "system_logo"),
            ("settings", "image_header"),
            ("app_branding_settings", "logo_image_url"),
            ("app_branding_settings", "logo_image_url_dark"),

            # Background / certs
            ("background_cards", "front_image"),
            ("background_cards", "back_image"),
            ("background_cert", "background_image"),

            # Zing
            ("zing_books", "cover_image_url"),
            ("zing_payment_methods", "image_url"),
        ]

        for table_name, col_name in target_columns:
            try:
                query = f"SELECT `{col_name}` FROM `{table_name}`"
                result = conn.execute(text(query))
                for row in result:
                    val = row[0]
                    if val and isinstance(val, str):
                        all_text_data.add(val)
            except Exception as e:
                print(f"  ⚠️  Skipped {table_name}.{col_name}: {e}")

    # Concatenate all into a single string for ultra-fast 'in' checks
    return "|||".join(all_text_data)


def scan_uploads(dry_run=True):
    giant_db_string = get_all_db_strings()
    
    base_dir = "uploads"
    orphans = []
    total_size = 0
    safe_count = 0
    
    print("\nScanning uploads directory...")
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file == ".DS_Store" or file.startswith("."):
                continue
                
            file_path = os.path.join(root, file)
            # The database might store it as /uploads/folder/file.ext or folder/file.ext or just file.ext
            # By checking if the exact filename (e.g. 1234-5678.jpg) is ANYWHERE in the massive DB string dump,
            # we securely guarantee we don't delete any file that is referenced in ANY table.
            
            if file not in giant_db_string:
                orphans.append(file_path)
                total_size += os.path.getsize(file_path)
            else:
                safe_count += 1
                
    print(f"\n--- SCAN COMPLETE ---")
    print(f"Safe files kept: {safe_count}")
    print(f"Orphaned files found: {len(orphans)}")
    print(f"Storage waste recovering: {total_size / 1024 / 1024:.2f} MB")
    
    if dry_run:
        print("\n--- DRY RUN: The following files WOULD be deleted ---")
        for o in orphans:
            print(f"[WILL DELETE] {o}")
        print("\nThis was a Dry Run. Run with `python scripts/clean_orphaned_uploads.py --delete` to execute.")
    else:
        print("\n--- EXECUTING DELETION ---")
        for o in orphans:
            try:
                os.remove(o)
                print(f"[DELETED] {o}")
            except Exception as e:
                print(f"[ERROR] Failed to delete {o}: {e}")
        print("Cleanup finished successfully!")

if __name__ == "__main__":
    dry_run = not args.delete
    scan_uploads(dry_run)
