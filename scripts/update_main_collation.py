import re

def process_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # We want to find all triple-quoted strings
    def replacer(match):
        s = match.group(0)
        
        # Only process CREATE TABLE strings
        if "CREATE TABLE" not in s.upper():
            return s
            
        # If it's already got the exact collation we want, skip
        if "COLLATE=utf8mb4_unicode_ci" in s.replace(" ", ""):
            return s
            
        # Is it a MySQL string? 
        # Signals: AUTO_INCREMENT (MySQL) vs AUTOINCREMENT (SQLite)
        # ENUM, TINYINT, ON UPDATE CURRENT_TIMESTAMP, DOUBLE, \` (backticks)
        is_mysql = any(k in s.upper() for k in [
            "AUTO_INCREMENT", 
            "ENUM(", 
            "TINYINT", 
            "ON UPDATE CURRENT_TIMESTAMP",
            "ON DUPLICATE KEY",
            "ENGINE=INNODB"
        ])
        
        # Results top students is also mysql
        if "results_top_students_display_settings" in s and "VARCHAR(10)" in s.upper():
            is_mysql = True
            
        if not is_mysql:
            return s

        # If it has the ENGINE but missing COLLATE
        if "ENGINE=INNODB" in s.upper().replace(" ", ""):
            # Replace `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4` with the COLLATE appended
            s = re.sub(
                r"(ENGINE\s*=\s*InnoDB\s*DEFAULT\s*CHARSET\s*=\s*utf8mb4)(?!\s*COLLATE)",
                r"\1 COLLATE=utf8mb4_unicode_ci",
                s,
                flags=re.IGNORECASE
            )
            return s
            
        # If it doesn't have ENGINE, we need to append it after the last closing `)` that belongs to CREATE TABLE
        # The string normally ends with `\n                    )` or `)`
        # We can find the last `)` before the closing quotes
        
        # Use a regex that finds the last `)` with trailing whitespace/quotes
        s = re.sub(
            r"\)(\s*(\"\"\"|'''))$", 
            r") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci\1", 
            s
        )
        return s

    # Regex to match triple quoted strings
    content = re.sub(r'\"\"\"[\s\S]*?\"\"\"', replacer, content)
    content = re.sub(r"\'\'\'[\s\S]*?\'\'\'", replacer, content)

    with open(filepath, "w") as f:
        f.write(content)

process_file("app/main.py")
print("Updated app/main.py successfully.")
