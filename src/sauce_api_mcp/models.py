from datetime import datetime
from typing import List, Dict, Optional, Union
from pydantic import BaseModel, Field, RootModel

# --- Account Models ---

class Organization(BaseModel):
    id: str
    name: str

class TeamSetting(BaseModel):
    live_only: bool
    real_devices: int
    virtual_machines: int

class Group(BaseModel):
    id: str
    name: str

class Team(BaseModel):
    id: str
    settings: TeamSetting
    group: Group
    is_default: bool
    name: str
    org_uuid: str

class Role(BaseModel):
    name: str
    role: int

class ResultItem(BaseModel):
    """
    Represents a single result item within the account information.
    """
    id: str
    email: str
    username: str
    first_name: str
    last_name: str
    is_active: bool
    # Assuming the settings object can contain various basic value types.
    organization: Organization
    # Assuming the group object can also contain various basic value types.
    roles: List[Role]
    teams: List[Team]

class AccountInfo(BaseModel):
    """
    The main model for the account information response.
    """

    # Assuming links is a dictionary of string keys and URL string values.
    links: Dict[str, Optional[str]]
    count: int
    results: List[ResultItem]

class LookupUsersLinks(BaseModel):
    next: Optional[str]
    previous: Optional[str]
    first: Optional[str]
    last: Optional[str]

class LookupUsers(BaseModel):
    links: LookupUsersLinks
    count: int
    results: List[ResultItem]

class ServiceAccountTeam(BaseModel):
    id: str
    name: str

class ServiceAccountCreator(BaseModel):
    id: str
    username: str
    email: str

class ServiceAccount(BaseModel):
    id: str
    username: str
    name: str
    team: ServiceAccountTeam
    creator: ServiceAccountCreator

class LookupServiceAccounts(BaseModel):
    links: LookupUsersLinks
    count: int
    results: List[ServiceAccount]

class ErrorResponse(BaseModel):
    error: str

class LookupTeamsResponse(BaseModel):
    links: LookupUsersLinks
    count: int
    results: List[Team]
