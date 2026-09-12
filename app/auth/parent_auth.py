from sqlalchemy.orm import Session
from ..models import Parent
from ..utils.phone import get_phone_variations
import bcrypt
import asyncio
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_parent_by_username(db: Session, username: str) -> Parent | None:
    """Get parent by username or phone number.

    Order matters. Phone numbers are matched *before* row IDs: a parent typing
    their own phone number that happens to equal another parent's ``id`` must
    not be handed that stranger's row. Phone matching also has to accept the
    formats actually present in the database (``096…``, ``96…``, ``+85596…``),
    which is why it goes through ``get_phone_variations`` instead of ``==``.

    Returns ``None`` when the input matches several parents — signing someone
    into "whichever row came first" is never the right answer.
    """
    if not username or not username.strip():
        return None

    username = username.strip()

    # 1. Exact username (the only truly unique identifier)
    parent = db.query(Parent).filter(Parent.username == username).first()
    if parent:
        return parent

    # 2. Phone number, in any of the formats the column may hold
    variations = get_phone_variations(username)
    if variations:
        matches = (
            db.query(Parent)
            .filter(
                (Parent.fatherPhone.in_(variations))
                | (Parent.motherPhone.in_(variations))
                | (Parent.gPhone.in_(variations))
            )
            .limit(2)
            .all()
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            # Ambiguous (e.g. legacy sibling rows sharing the father's phone).
            return None

    # 3. Row ID last, and only when nothing above matched
    if username.isdigit():
        parent = db.query(Parent).filter(Parent.id == int(username)).first()
        if parent:
            return parent

    return None

def verify_parent_password(parent: Parent, password: str) -> bool:
    """Verify parent password."""
    if not parent.password:
        return False
    # return pwd_context.verify(password, parent.password)
    if isinstance(password, str):
        password = password.encode('utf-8')
    hashed = parent.password.encode('utf-8') if isinstance(parent.password, str) else parent.password
    try:
        return bcrypt.checkpw(password, hashed)
    except ValueError:
        # Stored value is not a bcrypt hash (legacy import, plaintext, truncated
        # column). That is a failed login, not a 500.
        import logging

        logging.getLogger(__name__).warning(
            "Parent %s has a password that is not a valid bcrypt hash", parent.id
        )
        return False

async def async_verify_parent_password(parent: Parent, password: str) -> bool:
    """Async wrapper to prevent bcrypt from blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, verify_parent_password, parent, password)

def authenticate_parent(db: Session, username: str, password: str) -> Parent | None:
    """Authenticate parent with username and password."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Check if username is provided
    if not username or not username.strip():
        logger.warning("Parent authentication: Empty username provided")
        return None
    
    parent = get_parent_by_username(db, username)
    if not parent:
        logger.warning(f"Parent authentication: Parent not found with username: {username}")
        return None
    
    # Check if parent has a password set
    if not parent.password:
        logger.warning(f"Parent authentication: Parent {username} (ID: {parent.id}) has no password set")
        return None
    
    if not verify_parent_password(parent, password):
        logger.warning(f"Parent authentication: Invalid password for parent {username} (ID: {parent.id})")
        return None
    
    logger.info(f"Parent authentication: Success for parent {username} (ID: {parent.id})")
    return parent

async def async_authenticate_parent(db: Session, username: str, password: str) -> Parent | None:
    """Authenticate parent with username and password asynchronously."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Check if username is provided
    if not username or not username.strip():
        logger.warning("Parent authentication: Empty username provided")
        return None
    
    parent = get_parent_by_username(db, username)
    if not parent:
        logger.warning(f"Parent authentication: Parent not found with username: {username}")
        return None
    
    # Check if parent has a password set
    if not parent.password:
        logger.warning(f"Parent authentication: Parent {username} (ID: {parent.id}) has no password set")
        return None
        
    db.expunge(parent)
    db.rollback()
    
    is_valid = await async_verify_parent_password(parent, password)
    if not is_valid:
        logger.warning(f"Parent authentication: Invalid password for parent {username} (ID: {parent.id})")
        return None
    
    logger.info(f"Parent authentication: Success for parent {username} (ID: {parent.id})")
    return parent
