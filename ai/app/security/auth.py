from __future__ import annotations
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.security.models import User
from app.config import SECRET_KEY_BYTES, ALGORITHM, JWT_ISSUER
from app.common.database import get_user_from_db
from app.common.db_session import get_db

bearer_scheme = HTTPBearer()

async def get_current_user(
    auth: HTTPAuthorizationCredentials = Depends(bearer_scheme), 
    db: Session = Depends(get_db)
) -> User:
    
    from app.security.models import TokenPayload

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = auth.credentials

        payload = jwt.decode(
            token, 
            SECRET_KEY_BYTES, 
            algorithms=[ALGORITHM], 
            issuer=JWT_ISSUER
        )
        
        
        token_payload = TokenPayload(**payload)
        
        try:
            user_id = int(token_payload.sub)
        except ValueError:
            raise credentials_exception

    except JWTError as e:
        raise credentials_exception
    except AttributeError:
        raise credentials_exception
    except Exception as e:
        raise credentials_exception

    user = get_user_from_db(db=db, user_id=user_id)
    
    if user is None:
        raise credentials_exception
    
    return user

