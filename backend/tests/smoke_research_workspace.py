"""Called inside the isolated workspace transaction; no live writes or providers."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from app.models.journal import DecisionRevision
from app.models.workspace import WorkspaceAlert
from tests.test_research_workspace import declaration


async def verify(session, client, instrument):
    instrument_id = instrument.id
    data={**declaration(), "instrument_id":str(instrument_id)}
    base="/api/v1/workspace"
    first=await client.post(base+"/journal", json=data)
    assert first.status_code==200, first.text
    identifier=first.json()["decision_id"]
    replay=await client.post(base+"/journal", json=data)
    assert replay.json()["decision_id"]==identifier and replay.json()["inserted"] is False
    assert (await client.post(base+"/journal", json={**data,"title":"Contenu contradictoire"})).status_code==400
    revision={k:v for k,v in data.items() if k!="instrument_id"}
    revision.update(client_request_id=str(uuid4()),expected_version=1,status="invalidated",observations="Hypothèse revue après lecture")
    response=await client.post(f"{base}/journal/{identifier}/revisions", json=revision)
    assert response.status_code==200, response.text
    assert response.json()["revision"]["version"]==2
    assert (await client.post(f"{base}/journal/{identifier}/revisions",json={**revision,"client_request_id":str(uuid4())})).status_code==400
    history=(await client.get(f"{base}/journal/{identifier}")).json()
    assert [r["version"] for r in history["items"]]==[2,1]
    assert history["items"][1]["status"]=="considering"
    assert (await client.get(base+"/journal?status=considering")).json()["total"]==0
    assert (await client.get(base+"/journal?status=invalidated")).json()["total"]==1
    # Revision history can be read as of its original timestamp, without future updates.
    from app.services.journal import JournalService
    original=(await session.execute(select(DecisionRevision).where(DecisionRevision.decision_id==identifier,
        DecisionRevision.version==1))).scalar_one()
    assert (await JournalService(session).listing(as_of=original.recorded_at))["items"][0]["latest"]["status"]=="considering"
    today=datetime.now(UTC).date()
    assert (await client.get(base+"/briefing?day="+str(today+timedelta(days=1)))).status_code==400
    assert (await client.get(base+"/briefing?held_only=true")).status_code==400
    session.add(WorkspaceAlert(dedup_key="QA:future-proof",kind="publication",instrument_id=instrument_id,
        created_at=datetime.now(UTC)-timedelta(seconds=1), data={"title":"Future proof excluded","published_at":
            (datetime.now(UTC)+timedelta(days=1)).isoformat(),"page":"/analysis"}))
    await session.flush()
    briefing=(await client.get(base+"/briefing")).json()
    assert all(r["title"]!="Future proof excluded" for r in briefing["items"])
    assert briefing["notice"] and briefing["holdings_notice"]
    for family in ("sources","market","fx"):
        health=await client.get(base+"/collection-health?family="+family)
        assert health.status_code==200, health.text
        assert "scheduler" in health.json()
    print("Research workspace checks passed: journal retries/history/concurrency, as-of reading, briefing dates and collection health.")
