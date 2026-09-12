from sqlalchemy.orm import Session
from ..models.rbac import Permission, RolePermission
from ..models.organization import Role
import logging

logger = logging.getLogger(__name__)

REQUIRED_PERMISSIONS = [
    {"name": "AdminViewApp", "description": "View App settings"},
    {"name": "AdminUpdateApp", "description": "Update App settings"},
    {"name": "AdminDeleteApp", "description": "Delete App settings"},
    {
        "name": "ReviewStudentProfileEdits",
        "description": "Review, approve, or reject student profile edit requests",
    },
]

TARGET_ROLE_NAME = "Admin"

def seed_permissions(db: Session):
    """
    Seeds the database with required permissions and assigns them to the Admin role.
    """
    try:
        logger.info("Starting permission seeding...")
        
        # 1. Ensure permissions exist
        permissions_map = {}
        for perm_data in REQUIRED_PERMISSIONS:
            name = perm_data["name"]
            perm = db.query(Permission).filter(Permission.permission_name == name).first()
            if not perm:
                logger.info(f"Creating permission: {name}")
                perm = Permission(
                    permission_name=name,
                    description=perm_data["description"]
                )
                db.add(perm)
                db.flush() # Flush to get ID
            permissions_map[name] = perm

        # 2. Find Admin Role
        admin_role = db.query(Role).filter(Role.role_name == TARGET_ROLE_NAME).first()
        if not admin_role:
            logger.warning(f"Role '{TARGET_ROLE_NAME}' not found. Skipping assignment.")
            db.commit()
            return

        # 3. Assign permissions to Admin Role if not already assigned
        for name, perm in permissions_map.items():
            link = db.query(RolePermission).filter(
                RolePermission.role_id == admin_role.id,
                RolePermission.permission_id == perm.id
            ).first()
            
            if not link:
                logger.info(f"Assigning '{name}' to '{TARGET_ROLE_NAME}' role.")
                link = RolePermission(
                    role_id=admin_role.id,
                    permission_id=perm.id
                )
                db.add(link)
        
        db.commit()
        logger.info("Permission seeding completed successfully.")
        
    except Exception as e:
        logger.error(f"Error seeding permissions: {e}")
        db.rollback()
