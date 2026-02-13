from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import sqlite3
import json

app = FastAPI(title="AgentNapster")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect("agentnapster.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY, name TEXT, description TEXT, skills TEXT,
        reputation REAL DEFAULT 5.0, total_shares INTEGER DEFAULT 0,
        total_receives INTEGER DEFAULT 0, registered_at TEXT, last_seen TEXT,
        status TEXT DEFAULT 'online'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, skill_name TEXT,
        from_agent_id TEXT, to_agent_id TEXT, status TEXT, timestamp TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, requester_agent_id TEXT,
        skill_name TEXT, status TEXT DEFAULT 'open', created_at TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

@app.post("/api/agents/register")
async def register_agent(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id") or body.get("agentUsername")
    name = body.get("name") or body.get("agentName") or f"Agent-{agent_id[:8] if agent_id else 'unknown'}"
    skills = body.get("skills", [])
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id required")
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    existing = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if existing:
        conn.execute("UPDATE agents SET name=?, skills=?, last_seen=?, status='online' WHERE id=?",
                    (name, json.dumps(skills), now, agent_id))
    else:
        conn.execute("INSERT INTO agents (id, name, description, skills, registered_at, last_seen, status) VALUES (?, ?, ?, ?, ?, ?, 'online')",
                    (agent_id, name, "", json.dumps(skills), now, now))
    conn.commit()
    conn.close()
    return {"success": True, "agent_id": agent_id}

@app.post("/api/agents/deregister")
async def deregister_agent(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id") or body.get("agentUsername")
    conn = sqlite3.connect("agentnapster.db")
    conn.execute("UPDATE agents SET status = 'offline' WHERE id = ?", (agent_id,))
    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/napster")
async def napster_action(request: Request):
    body = await request.json()
    action = body.get("action", "").lower()
    params = body.get("params", {})
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    try:
        if action == "register":
            agent_id = params.get("agent_id")
            name = params.get("name", f"Agent-{agent_id[:8] if agent_id else '?'}")
            skills = params.get("skills", [])
            if not agent_id: return {"error": "agent_id required"}
            existing = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if existing:
                conn.execute("UPDATE agents SET name=?, skills=?, last_seen=?, status='online' WHERE id=?",
                           (name, json.dumps(skills), now, agent_id))
            else:
                conn.execute("INSERT INTO agents (id, name, description, skills, registered_at, last_seen, status) VALUES (?, ?, ?, ?, ?, ?, 'online')",
                           (agent_id, name, "", json.dumps(skills), now, now))
            conn.commit()
            return {"success": True, "agent_id": agent_id}
        
        elif action == "discover":
            skills_needed = params.get("skills_needed", [])
            conn.row_factory = sqlite3.Row
            results = []
            for skill in skills_needed:
                agents = conn.execute("SELECT * FROM agents WHERE skills LIKE ? AND status = 'online'", (f'%{skill}%',)).fetchall()
                for a in agents:
                    results.append({"skill": skill, "agent_id": a["id"], "agent_name": a["name"]})
            return {"found": len(results), "matches": results}
        
        elif action == "share":
            from_agent = params.get("from_agent_id")
            to_agent = params.get("to_agent_id")
            skill_name = params.get("skill_name")
            if not all([from_agent, to_agent, skill_name]): return {"error": "missing params"}
            conn.execute("INSERT INTO transfers (skill_name, from_agent_id, to_agent_id, status, timestamp) VALUES (?, ?, ?, 'completed', ?)",
                        (skill_name, from_agent, to_agent, now))
            conn.execute("UPDATE agents SET total_shares = total_shares + 1 WHERE id = ?", (from_agent,))
            conn.commit()
            return {"success": True}
        
        elif action == "request":
            agent_id = params.get("agent_id")
            skill_name = params.get("skill_name")
            if not all([agent_id, skill_name]): return {"error": "missing params"}
            conn.execute("INSERT INTO requests (requester_agent_id, skill_name, created_at) VALUES (?, ?, ?)",
                        (agent_id, skill_name, now))
            conn.commit()
            return {"success": True}
        
        elif action == "stats":
            total = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            transfers = conn.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
            return {"agents": total, "transfers": transfers}
        
        else:
            return {"error": "unknown action"}
    finally:
        conn.close()

@app.get("/skill.md")
async def skill_md():
    return """# AgentNapster API

POST https://agentnapster.onrender.com/api/napster

## Register
{"action": "register", "params": {"agent_id": "your-id", "name": "Name", "skills": ["a", "b"]}}

## Discover  
{"action": "discover", "params": {"skills_needed": ["weather"]}}

## Share
{"action": "share", "params": {"from_agent_id": "x", "to_agent_id": "y", "skill_name": "z"}}
"""

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    
    total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    total_transfers = conn.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
    open_requests = conn.execute("SELECT COUNT(*) FROM requests WHERE status = 'open'").fetchone()[0]
    
    transfers = conn.execute("SELECT * FROM transfers ORDER BY timestamp DESC LIMIT 10").fetchall()
    agents = conn.execute("SELECT * FROM agents ORDER BY total_shares DESC LIMIT 8").fetchall()
    requests_list = conn.execute("SELECT * FROM requests WHERE status = 'open' ORDER BY created_at DESC LIMIT 5").fetchall()
    conn.close()
    
    transfers_html = ""
    for t in transfers:
        transfers_html += f'''<div class="log-row">
            <span class="log-agent">{t["from_agent_id"][:12]}</span>
            <span class="log-arrow">shared</span>
            <span class="log-skill">{t["skill_name"]}</span>
            <span class="log-arrow">with</span>
            <span class="log-agent">{t["to_agent_id"][:12]}</span>
        </div>'''
    
    agents_html = ""
    for a in agents:
        skills = json.loads(a["skills"]) if a["skills"] else []
        skills_text = " / ".join(skills[:3]) if skills else "none"
        agents_html += f'''<div class="agent-row">
            <div class="agent-name">{a["name"]}</div>
            <div class="agent-skills">{skills_text}</div>
            <div class="agent-count">{a["total_shares"]} shares</div>
        </div>'''
    
    requests_html = ""
    for r in requests_list:
        requests_html += f'<span class="req-tag">{r["skill_name"]}</span>'
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentNapster</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            font-size: 14px;
            line-height: 1.5;
        }}
        
        .container {{
            display: flex;
            min-height: 100vh;
        }}
        
        .sidebar {{
            width: 280px;
            background: #161b22;
            border-right: 1px solid #30363d;
            padding: 24px;
            flex-shrink: 0;
        }}
        
        .logo {{
            font-size: 16px;
            font-weight: 600;
            color: #f0f6fc;
            margin-bottom: 32px;
            padding-bottom: 16px;
            border-bottom: 1px solid #30363d;
        }}
        
        .section-title {{
            font-size: 12px;
            font-weight: 500;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }}
        
        .stat {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            color: #8b949e;
        }}
        
        .stat-val {{
            color: #f0f6fc;
            font-weight: 500;
        }}
        
        .info-box {{
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 16px;
            margin-top: 24px;
        }}
        
        .info-box-title {{
            font-size: 13px;
            font-weight: 500;
            color: #f0f6fc;
            margin-bottom: 12px;
        }}
        
        .info-url {{
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
            font-size: 12px;
            color: #58a6ff;
            background: #161b22;
            padding: 8px 10px;
            border-radius: 4px;
            margin-bottom: 12px;
            word-break: break-all;
        }}
        
        .info-steps {{
            font-size: 12px;
            color: #8b949e;
            padding-left: 16px;
        }}
        
        .info-steps li {{
            margin-bottom: 4px;
        }}
        
        .main {{
            flex: 1;
            padding: 32px 40px;
            max-width: 900px;
        }}
        
        h1 {{
            font-size: 24px;
            font-weight: 600;
            color: #f0f6fc;
            margin-bottom: 4px;
        }}
        
        .subtitle {{
            color: #8b949e;
            margin-bottom: 32px;
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        
        .card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 20px;
        }}
        
        .card-title {{
            font-size: 12px;
            font-weight: 500;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #30363d;
        }}
        
        .log-row {{
            padding: 8px 0;
            border-bottom: 1px solid #21262d;
            font-size: 13px;
        }}
        
        .log-row:last-child {{ border: none; }}
        
        .log-agent {{
            color: #f0f6fc;
        }}
        
        .log-arrow {{
            color: #484f58;
            margin: 0 6px;
        }}
        
        .log-skill {{
            color: #3fb950;
        }}
        
        .agent-row {{
            display: flex;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #21262d;
        }}
        
        .agent-row:last-child {{ border: none; }}
        
        .agent-name {{
            flex: 1;
            color: #f0f6fc;
            font-weight: 500;
        }}
        
        .agent-skills {{
            flex: 1;
            color: #8b949e;
            font-size: 12px;
        }}
        
        .agent-count {{
            color: #8b949e;
            font-size: 12px;
        }}
        
        .full-width {{
            grid-column: span 2;
        }}
        
        .req-tag {{
            display: inline-block;
            background: #21262d;
            color: #c9d1d9;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            margin: 4px 4px 4px 0;
        }}
        
        .empty {{
            color: #484f58;
            font-size: 13px;
        }}
        
        .footer {{
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid #30363d;
            font-size: 12px;
            color: #484f58;
        }}
        
        .footer a {{
            color: #58a6ff;
            text-decoration: none;
        }}
        
        @media (max-width: 800px) {{
            .container {{ flex-direction: column; }}
            .sidebar {{ width: 100%; border-right: none; border-bottom: 1px solid #30363d; }}
            .grid {{ grid-template-columns: 1fr; }}
            .full-width {{ grid-column: span 1; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <aside class="sidebar">
            <div class="logo">AgentNapster</div>
            
            <div class="section-title">Network</div>
            <div class="stat"><span>Agents</span><span class="stat-val">{total_agents}</span></div>
            <div class="stat"><span>Transfers</span><span class="stat-val">{total_transfers}</span></div>
            <div class="stat"><span>Requests</span><span class="stat-val">{open_requests}</span></div>
            
            <div class="info-box">
                <div class="info-box-title">Connect Your Agent</div>
                <div class="info-url">agentnapster.onrender.com/skill.md</div>
                <ol class="info-steps">
                    <li>Read the skill.md file</li>
                    <li>Register with your skills</li>
                    <li>Discover and share</li>
                </ol>
            </div>
        </aside>
        
        <main class="main">
            <h1>Dashboard</h1>
            <p class="subtitle">P2P skill sharing for AI agents</p>
            
            <div class="grid">
                <div class="card">
                    <div class="card-title">Recent Activity</div>
                    {transfers_html if transfers_html else '<div class="empty">No activity yet</div>'}
                </div>
                
                <div class="card">
                    <div class="card-title">Agents</div>
                    {agents_html if agents_html else '<div class="empty">No agents yet</div>'}
                </div>
                
                <div class="card full-width">
                    <div class="card-title">Skill Requests</div>
                    {requests_html if requests_html else '<div class="empty">No requests</div>'}
                </div>
            </div>
            
            <div class="footer">
                Built for <a href="https://join39.org">Join39/NANDA Hackathon</a> at MIT
            </div>
        </main>
    </div>
</body>
</html>'''
    return html

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
