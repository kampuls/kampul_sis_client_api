import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Find all CREATE TABLE statements specifically inside MySQL blocks
    # Actually, we can just find any CREATE TABLE inside """ ... """ and check if it has MySQL specific syntax 
    # like AUTO_INCREMENT or ENUM, or just replace the last `)` before `"""` with the engine string.
    # But some might already have ENGINE=InnoDB...
    
    # Let's use a regex to replace `)` right before `"""` or `'''` for CREATE TABLEs that are MySQL only.
    # Since we know the tables in main.py under `if is_mysql` have `AUTO_INCREMENT` or we can just 
    # look at `app/main.py` and `app/core/migrations.py` and manually replace.

    # It's safer to use Python's AST or just carefully crafted regex.
    # Let's replace the regex:
    # 1. Any existing ENGINE=...
    content = re.sub(
        r"(\)\s*ENGINE\s*=\s*InnoDB\s*(?:DEFAULT\s*)?CHARSET\s*=\s*utf8mb4)(?!\s*COLLATE)",
        r"\1 COLLATE=utf8mb4_unicode_ci",
        content,
        flags=re.IGNORECASE
    )

    # 2. For MySQL tables without ENGINE clause. Most use AUTO_INCREMENT, so let's match CREATE TABLE .* AUTO_INCREMENT .* \) ""\"
    def add_engine(match):
        text = match.group(0)
        # If it's already got ENGINE, skip
        if "ENGINE" in text.upper():
            return text
        # Otherwise, insert ENGINE before the final closing quotes
        return re.sub(r"\)\s*(\"\"\"|''')", r") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci\n\1", text)
        
    # Find all multi-line strings
    content = re.sub(r'\"\"\"[\s\S]*?\"\"\"', add_engine, content)
    content = re.sub(r"\'\'\'[\s\S]*?\'\'\'", add_engine, content)

    # Now let's handle the specific ones in main.py that don't have AUTO_INCREMENT but are MySQL
    # e.g., results_top_students_display_settings
    # The `add_engine` function applied to ALL triple-quoted strings! That includes SQLite strings.
    # So we should only apply it if "AUTO_INCREMENT" or "ENUM" or "COMMENT" or "ON DUPLICATE KEY" is inside, 
    # or if we explicitly know it's a MySQL string.
    pass

# We will write a safer script
with open('scripts/update_collation.py', 'w') as f:
    f.write('''import re
import os

def process_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # 1. Update existing ENGINE clauses
    content = re.sub(
        r"(\)\s*ENGINE\s*=\s*InnoDB\s*(?:DEFAULT\s*)?CHARSET\s*=\s*utf8mb4)(?!\s*COLLATE)",
        r"\\1 COLLATE=utf8mb4_unicode_ci",
        content,
        flags=re.IGNORECASE
    )

    # 2. Add ENGINE to MySQL CREATE TABLE strings
    # A string is a MySQL string if it's called after `if is_mysql:` or contains `AUTO_INCREMENT`
    def replacer(match):
        s = match.group(0)
        if "CREATE TABLE" not in s.upper():
            return s
        if "ENGINE" in s.upper():
            return s
        
        # Heuristic: MySQL strings have AUTO_INCREMENT, ENUM, TINYINT, DATETIME ON UPDATE
        is_mysql = any(k in s.upper() for k in ["AUTO_INCREMENT", "ENUM(", "TINYINT", "ON UPDATE CURRENT_TIMESTAMP"])
        
        # Also check contexts where it's explicitly MySQL but lacks those
        if "results_top_students_display_settings" in s and "VARCHAR(10)" in s.upper():
            is_mysql = True
            
        if is_mysql:
            # Add engine before the ending quotes
            s = re.sub(r"\)\s*(\"\"\"|''')", r") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci\\n                    \\1", s)
        return s

    content = re.sub(r'\"\"\"[\s\S]*?\"\"\"', replacer, content)
    content = re.sub(r"\'\'\'[\s\S]*?\'\'\'", replacer, content)

    with open(filepath, "w") as f:
        f.write(content)

process_file("app/main.py")
process_file("app/core/migrations.py")
print("Successfully added COLLATION to CREATE TABLE statements")
''')
