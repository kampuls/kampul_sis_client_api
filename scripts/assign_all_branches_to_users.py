"""
Script to bulk-assign all branches to users
Usage: 
  python assign_all_branches_to_users.py --role-id 3
  python assign_all_branches_to_users.py --user-ids 1,2,3
  
Common role IDs:
  1 = Admin
  2 = Manager  
  3 = Teacher
  4 = Staff
  5 = Parent
  6 = Student
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from app.core.database import engine
from app.core.config import settings

def assign_all_branches_to_users(user_ids=None, role_id=None):
    """
    Assign all active branches to specified users or role.
    
    Args:
        user_ids: List of specific user IDs
        role_id: Filter by role ID (e.g., 3 for teachers)
    """
    print("🔧 Bulk Branch Assignment Tool")
    print("=" * 50)
    
    with engine.connect() as conn:
        # Get all active branches
        branches_query = text("""
            SELECT id, name_kh FROM branches 
            WHERE is_active = 1 
            ORDER BY id
        """)
        branches = conn.execute(branches_query).fetchall()
        
        if not branches:
            print("❌ No active branches found!")
            return
        
        print(f"📍 Found {len(branches)} active branches:")
        for b in branches:
            print(f"   - {b[0]}: {b[1]}")
        print()
        
        # Get target users
        if user_ids:
            users_query = text(f"""
                SELECT id, name_kh, workplace, role_id FROM users 
                WHERE id IN ({','.join(map(str, user_ids))})
                AND is_active = 1
            """)
        elif role_id:
            users_query = text(f"""
                SELECT id, name_kh, workplace, role_id FROM users 
                WHERE role_id = {role_id}
                AND is_active = 1
                ORDER BY id
            """)
        else:
            print("❌ Must specify --user-ids or --role-id")
            print()
            print("Common role IDs:")
            print("  1 = Admin")
            print("  2 = Manager")  
            print("  3 = Teacher")
            print("  4 = Staff")
            print("  5 = Parent")
            print("  6 = Student")
            return
            
        users = conn.execute(users_query).fetchall()
        
        if not users:
            print("❌ No matching users found!")
            return
        
        print(f"👥 Found {len(users)} matching users:")
        for u in users:
            print(f"   - {u[0]}: {u[1]} (workplace: {u[2]}, role: {u[3]})")
        print()
        print(f"⚠️  This will assign ALL {len(branches)} branches to {len(users)} users.")
        confirm = input("Continue? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("❌ Cancelled")
            return
        
        # Assign branches to users
        total_added = 0
        for user in users:
            user_id = user[0]
            user_workplace = user[2]
            
            print(f"⏳ Processing user {user_id}...")
            
            # Get branches already assigned
            existing_query = text("""
                SELECT branch_id FROM attendance__allowed_branches 
                WHERE user_id = :user_id
            """)
            existing = set(row[0] for row in conn.execute(existing_query, {"user_id": user_id}))
            
            # Add branches that aren't already assigned
            added_count = 0
            for branch in branches:
                branch_id = branch[0]
                
                # Skip if it's their primary workplace (already allowed)
                if branch_id == user_workplace:
                    continue
                
                # Skip if already in allowed branches
                if branch_id in existing:
                    continue
                
                # Add to allowed branches
                insert_query = text("""
                    INSERT INTO attendance__allowed_branches (user_id, branch_id)
                    VALUES (:user_id, :branch_id)
                """)
                conn.execute(insert_query, {"user_id": user_id, "branch_id": branch_id})
                added_count += 1
            
            total_added += added_count
            print(f"   ✅ Added {added_count} new branch(es)")
        
        conn.commit()
        print()
        print("=" * 50)
        print(f"🎉 Successfully added {total_added} branch assignments!")
        print()
        print("✅ Users can now scan QR codes at any of their assigned branches!")
        print()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Bulk assign branches to users')
    parser.add_argument('--user-ids', type=str, help='Comma-separated user IDs')
    parser.add_argument('--role-id', type=int, help='Role ID (e.g., 3 for teachers)')
    
    args = parser.parse_args()
    
    user_ids = None
    if args.user_ids:
        user_ids = [int(x.strip()) for x in args.user_ids.split(',')]
    
    assign_all_branches_to_users(user_ids=user_ids, role_id=args.role_id)
