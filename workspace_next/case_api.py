"""Case API for isolated workspace development. Not mounted by main.py yet."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from workspace_next import case_store as cases
from workspace_next import queries
from backend import auth, event_store as store
from workspace_next import system_accounts

router = APIRouter(tags=['Case workspace'])


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    actor: str = Field(default='',max_length=200)  # deprecated: ignored, the session names the analyst
    request_key: str = Field(min_length=1,max_length=128)


class Create(Command):
    title: str = Field(min_length=1,max_length=240)
    owner: str = Field(default='',max_length=200)
    priority: str = 'Medium'
    notes: str = Field(default='',max_length=20000)


class Edit(Command):
    expected_version: int = Field(ge=1)
    changes: dict


class Link(Command):
    expected_version: int = Field(ge=1)
    kind: str
    target: str = Field(min_length=1,max_length=256)
    reason: str = Field(min_length=1,max_length=2000)


class FromFinding(Create):
    request_key: str = Field(min_length=1,max_length=100)
    finding_id: int = Field(ge=1)
    reason: str = Field(min_length=1,max_length=2000)
    include_account: bool = False


class FindingStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = ''
    analyst: str = ''  # deprecated: ignored, the session names the analyst
    reason: str = ''


def signed(request, body):
    """Body with its actor replaced by the signed-in analyst."""
    return body.model_copy(update={'actor': auth.session_user(request, body.actor)})


def call(operation,*args,**kwargs):
    try:
        return operation(*args,**kwargs)
    except cases.CaseNotFound as exc:
        raise HTTPException(404,'Case or evidence not found') from exc
    except cases.CaseConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except (ValueError,TypeError) as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get('/cases')
def listing(limit: int = Query(50,ge=1,le=100), before_time: str | None = None,
            before_id: str | None = None):
    if bool(before_time) != bool(before_id):
        raise HTTPException(422,'Both cursor fields are required')
    return call(cases.list_cases,limit,[before_time,before_id] if before_time else None)


@router.post('/cases',status_code=201)
def create(body: Create,request: Request):
    return call(cases.create,**signed(request,body).model_dump())


def create_from_finding(body):
    with store.transaction():
        finding=queries.finding(body.finding_id)
        values=body.model_dump(exclude={'finding_id','reason','include_account'})
        row=cases.create(**values,context={'finding_id':body.finding_id,'reason':body.reason,
                                         'include_account':body.include_account})
        row=cases.link(row['id'],row['version'],body.actor,body.request_key+':finding',
                       'finding',str(body.finding_id),body.reason)
        if body.include_account:
            row=cases.link(row['id'],row['version'],body.actor,body.request_key+':account',
                           'account',finding['user_id'],'Account referenced by selected finding')
        return row


@router.post('/cases/from-finding',status_code=201)
def from_finding(body: FromFinding,request: Request):
    return call(create_from_finding,signed(request,body))


@router.get('/cases/{case_id}')
def get(case_id: str,request: Request):
    return call(cases.get,case_id)


@router.patch('/cases/{case_id}')
def edit(case_id: str,body: Edit,request: Request):
    return call(cases.update,case_id,**signed(request,body).model_dump())


@router.post('/cases/{case_id}/links')
def link(case_id: str,body: Link,request: Request):
    return call(cases.link,case_id,**signed(request,body).model_dump())


@router.get('/events/{event_id}')
def evidence(event_id: int):
    return call(cases.evidence,event_id)


def cursor(time,identifier):
    if bool(time)!=bool(identifier):
        raise ValueError('Both cursor fields are required')
    return [time,identifier] if time else None


@router.get('/findings')
def findings(limit: int = Query(50,ge=1,le=500), before_time: str | None = None,
             before_id: str | None = None,category: str='security',status: str='Open',
             provider: str | None=None,account: str | None=None,start: str | None=None,end: str | None=None,entity_context: str | None=None,
             triage: str | None=None,learning: str='include'):
    return call(lambda: queries.findings(limit,cursor(before_time,before_id),category,status,provider,account,start,end,entity_context,triage,learning))


@router.get('/findings/{finding_id}')
def finding(finding_id: int):
    return call(queries.finding,finding_id)


@router.post('/findings/{finding_id}/status')
def finding_status(finding_id: int,body: FindingStatus,request: Request):
    return call(queries.set_status,finding_id,body.status,auth.session_user(request,body.analyst),body.reason)


@router.get('/workspace/accounts')
def accounts():
    declared=system_accounts.declared(store.DB_PATH)
    return [{**a,'infrastructure':system_accounts.is_infrastructure(a.get('account_label'),a.get('account_kind'),a.get('source'),declared)}
            for a in store.account_directory().values()]


@router.get('/workspace/people')
def people():
    from backend import identity_links
    return call(identity_links.list_people)


@router.get('/cases/{case_id}/timeline')
def timeline(case_id: str,limit: int=Query(50,ge=1,le=100),before_time: str | None=None,
             before_id: str | None=None,provider: str | None=None,start: str | None=None,end: str | None=None):
    return call(lambda: queries.timeline(case_id,limit,cursor(before_time,before_id),provider,start,end))
