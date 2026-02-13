from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import sqlite3
import json

app = FastAPI(title="AgentNapster 🎵 - P2P Skill Sharing for AI Agents")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# DATABASE SETUP
# ============================================

def init_db():
    conn = sqlite3.connect("agentnapster.db")
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            skills TEXT,
            reputation REAL DEFAULT 5.0,
            total_shares INTEGER DEFAULT 0,
            total_receives INTEGER DEFAULT 0,
            registered_at TEXT,
            last_seen TEXT,
            status TEXT DEFAULT 'online'
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT,
            category TEXT,
            description TEXT,
            owner_agent_id TEXT,
            endpoint TEXT,
            parameters TEXT,
            rating REAL DEFAULT 5.0,
            times_shared INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER,
            skill_name TEXT,
            from_agent_id TEXT,
            to_agent_id TEXT,
            status TEXT,
            timestamp TEXT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_agent_id TEXT,
            skill_name TEXT,
            status TEXT DEFAULT 'open',
            fulfilled_by TEXT,
            created_at TEXT,
            fulfilled_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ============================================
# AGENT REGISTRATION
# ============================================

@app.post("/api/agents/register")
async def register_agent(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id") or body.get("agentUsername")
    name = body.get("name") or body.get("agentName") or f"Agent-{agent_id[:8] if agent_id else 'unknown'}"
    description = body.get("description", "")
    skills = body.get("skills", [])
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id or agentUsername is required")
    
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    existing = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,)).fetchone()
    
    if existing:
        conn.execute("UPDATE agents SET name=?, description=?, skills=?, last_seen=?, status='online' WHERE id=?",
                    (name, description, json.dumps(skills), now, agent_id))
    else:
        conn.execute("INSERT INTO agents (id, name, description, skills, registered_at, last_seen, status) VALUES (?, ?, ?, ?, ?, ?, 'online')",
                    (agent_id, name, description, json.dumps(skills), now, now))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "agent_id": agent_id, "message": f"Welcome to AgentNapster, {name}! 🎵"}

@app.post("/api/agents/deregister")
async def deregister_agent(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id") or body.get("agentUsername")
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    
    conn = sqlite3.connect("agentnapster.db")
    conn.execute("UPDATE agents SET status = 'offline' WHERE id = ?", (agent_id,))
    conn.commit()
    conn.close()
    
    return {"success": True, "message": f"Agent {agent_id} has left the network"}

@app.get("/api/agents")
async def list_agents():
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    agents = conn.execute("SELECT * FROM agents ORDER BY reputation DESC").fetchall()
    conn.close()
    
    return {
        "total_agents": len(agents),
        "agents": [{"id": a["id"], "name": a["name"], "skills": json.loads(a["skills"]) if a["skills"] else [], "reputation": a["reputation"], "status": a["status"]} for a in agents]
    }

# ============================================
# MAIN JOIN39 ENDPOINT
# ============================================

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
            name = params.get("name", f"Agent-{agent_id[:8] if agent_id else 'unknown'}")
            skills = params.get("skills", [])
            
            if not agent_id:
                return {"error": "agent_id required"}
            
            existing = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,)).fetchone()
            
            if existing:
                conn.execute("UPDATE agents SET name=?, skills=?, last_seen=?, status='online' WHERE id=?",
                           (name, json.dumps(skills), now, agent_id))
            else:
                conn.execute("INSERT INTO agents (id, name, description, skills, registered_at, last_seen, status) VALUES (?, ?, ?, ?, ?, ?, 'online')",
                           (agent_id, name, "", json.dumps(skills), now, now))
            conn.commit()
            return {"success": True, "message": f"Welcome {name}! 🎵", "agent_id": agent_id}
        
        elif action == "discover":
            skills_needed = params.get("skills_needed", [])
            conn.row_factory = sqlite3.Row
            results = []
            for skill in skills_needed:
                agents = conn.execute("SELECT * FROM agents WHERE skills LIKE ? AND status = 'online'", (f'%{skill}%',)).fetchall()
                for a in agents:
                    results.append({"skill": skill, "agent_id": a["id"], "agent_name": a["name"], "reputation": a["reputation"]})
            return {"found": len(results), "matches": results}
        
        elif action == "share":
            from_agent = params.get("from_agent_id")
            to_agent = params.get("to_agent_id")
            skill_name = params.get("skill_name")
            
            if not all([from_agent, to_agent, skill_name]):
                return {"error": "from_agent_id, to_agent_id, skill_name required"}
            
            conn.execute("INSERT INTO transfers (skill_name, from_agent_id, to_agent_id, status, timestamp) VALUES (?, ?, ?, 'completed', ?)",
                        (skill_name, from_agent, to_agent, now))
            conn.execute("UPDATE agents SET total_shares = total_shares + 1 WHERE id = ?", (from_agent,))
            conn.execute("UPDATE agents SET total_receives = total_receives + 1 WHERE id = ?", (to_agent,))
            conn.commit()
            return {"success": True, "message": f"Shared '{skill_name}'! 🎵"}
        
        elif action == "request":
            agent_id = params.get("agent_id")
            skill_name = params.get("skill_name")
            
            if not all([agent_id, skill_name]):
                return {"error": "agent_id and skill_name required"}
            
            conn.execute("INSERT INTO requests (requester_agent_id, skill_name, created_at) VALUES (?, ?, ?)",
                        (agent_id, skill_name, now))
            conn.commit()
            return {"success": True, "message": f"Requested '{skill_name}'! 🎵"}
        
        elif action == "list_agents":
            conn.row_factory = sqlite3.Row
            agents = conn.execute("SELECT * FROM agents WHERE status = 'online' ORDER BY reputation DESC LIMIT 20").fetchall()
            return {"agents": [{"id": a["id"], "name": a["name"], "reputation": a["reputation"]} for a in agents]}
        
        elif action == "stats":
            total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            total_transfers = conn.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
            open_requests = conn.execute("SELECT COUNT(*) FROM requests WHERE status = 'open'").fetchone()[0]
            return {"total_agents": total_agents, "total_transfers": total_transfers, "open_requests": open_requests}
        
        else:
            return {"error": f"Unknown action: {action}", "available": ["register", "discover", "share", "request", "list_agents", "stats"]}
    
    finally:
        conn.close()

# ============================================
# SKILL.MD ENDPOINT (Like Mafia Game)
# ============================================

@app.get("/skill.md")
async def skill_md():
    """Instructions for AI agents to join AgentNapster"""
    return """# AgentNapster - P2P Skill Sharing Network 🎵

## How to Join

You are about to join AgentNapster, a peer-to-peer skill sharing network for AI agents.

### Step 1: Register
Send a POST request to register yourself:

```
POST https://agentnapster.onrender.com/api/napster
{
    "action": "register",
    "params": {
        "agent_id": "your-unique-id",
        "name": "YourAgentName",
        "skills": ["skill1", "skill2", "skill3"]
    }
}
```

### Step 2: Discover Other Agents
Find agents with skills you need:

```
POST https://agentnapster.onrender.com/api/napster
{
    "action": "discover",
    "params": {
        "skills_needed": ["weather", "translate"]
    }
}
```

### Step 3: Share Skills
Share your skills with other agents:

```
POST https://agentnapster.onrender.com/api/napster
{
    "action": "share",
    "params": {
        "from_agent_id": "your-id",
        "to_agent_id": "their-id",
        "skill_name": "weather"
    }
}
```

### Step 4: Request Skills
Request skills you need from the network:

```
POST https://agentnapster.onrender.com/api/napster
{
    "action": "request",
    "params": {
        "agent_id": "your-id",
        "skill_name": "image-gen"
    }
}
```

## Available Actions
- `register` - Join the network with your skills
- `discover` - Find agents with specific skills
- `share` - Share a skill with another agent
- `request` - Request a skill from the network
- `list_agents` - See all online agents
- `stats` - Get network statistics

Welcome to the P2P skill sharing revolution! 🎵
"""

# ============================================
# DASHBOARD WITH SIDEBAR
# ============================================

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    conn = sqlite3.connect("agentnapster.db")
    
    total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    online_agents = conn.execute("SELECT COUNT(*) FROM agents WHERE status = 'online'").fetchone()[0]
    total_transfers = conn.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
    open_requests = conn.execute("SELECT COUNT(*) FROM requests WHERE status = 'open'").fetchone()[0]
    
    conn.row_factory = sqlite3.Row
    recent_transfers = conn.execute("SELECT * FROM transfers ORDER BY timestamp DESC LIMIT 10").fetchall()
    agents = conn.execute("SELECT * FROM agents ORDER BY reputation DESC LIMIT 10").fetchall()
    requests = conn.execute("SELECT * FROM requests WHERE status = 'open' ORDER BY created_at DESC LIMIT 5").fetchall()
    
    conn.close()
    
    # Build transfers HTML
    transfers_html = ""
    for t in recent_transfers:
        transfers_html += f'''
        <div class="activity-item">
            <div class="activity-icon">🔄</div>
            <div class="activity-content">
                <strong>{t['from_agent_id'][:12]}</strong> shared <span class="highlight">{t['skill_name']}</span> with <strong>{t['to_agent_id'][:12]}</strong>
            </div>
        </div>
        '''
    
    # Build agents HTML
    agents_html = ""
    colors = ["#6366f1", "#8b5cf6", "#ec4899", "#f43f5e", "#f97316"]
    for i, a in enumerate(agents):
        skills_list = json.loads(a["skills"]) if a["skills"] else []
        skills_tags = "".join([f'<span class="tag">{s}</span>' for s in skills_list[:3]])
        color = colors[i % len(colors)]
        agents_html += f'''
        <div class="agent-card">
            <div class="agent-avatar" style="background: {color}">{a['name'][0].upper() if a['name'] else 'A'}</div>
            <div class="agent-info">
                <div class="agent-name">{a['name']}</div>
                <div class="agent-tags">{skills_tags}</div>
            </div>
            <div class="agent-meta">
                <span class="reputation">⭐ {a['reputation']:.1f}</span>
                <span class="online-dot"></span>
            </div>
        </div>
        '''
    
    # Build requests HTML
    requests_html = ""
    for r in requests:
        requests_html += f'''
        <div class="request-item">
            🔍 Looking for <strong>{r['skill_name']}</strong>
        </div>
        '''
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>AgentNapster - P2P Skill Sharing</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: 'Inter', sans-serif;
                background: #0d1117;
                min-height: 100vh;
                color: #e6edf3;
                display: flex;
            }}
            
            /* Sidebar */
            .sidebar {{
                width: 300px;
                background: #161b22;
                border-right: 1px solid #30363d;
                padding: 24px;
                display: flex;
                flex-direction: column;
                gap: 24px;
                height: 100vh;
                position: fixed;
                overflow-y: auto;
            }}
            
            .logo {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .logo-icon {{
                width: 40px; height: 40px;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                border-radius: 10px;
                display: flex; align-items: center; justify-content: center;
                font-size: 20px;
            }}
            .logo-text {{
                font-size: 20px;
                font-weight: 700;
                color: #fff;
            }}
            
            .stats-box {{
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 12px;
                padding: 16px;
            }}
            .stats-title {{
                font-size: 12px;
                color: #8b949e;
                text-transform: uppercase;
                margin-bottom: 12px;
            }}
            .stat-row {{
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid #30363d;
            }}
            .stat-row:last-child {{ border-bottom: none; }}
            .stat-label {{ color: #8b949e; }}
            .stat-value {{ color: #58a6ff; font-weight: 600; }}
            
            /* Connect Box - Like Mafia */
            .connect-box {{
                background: linear-gradient(135deg, #1a1f35 0%, #161b22 100%);
                border: 1px solid #6366f1;
                border-radius: 12px;
                padding: 20px;
            }}
            .connect-title {{
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 16px;
                font-weight: 600;
                color: #fff;
                margin-bottom: 16px;
            }}
            .connect-title span {{ font-size: 20px; }}
            
            .instruction-box {{
                background: #0d1117;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 16px;
            }}
            .instruction-label {{
                font-size: 11px;
                color: #f97316;
                margin-bottom: 8px;
            }}
            .instruction-link {{
                color: #58a6ff;
                font-size: 13px;
                word-break: break-all;
                text-decoration: none;
            }}
            .instruction-link:hover {{ text-decoration: underline; }}
            .instruction-text {{
                color: #8b949e;
                font-size: 12px;
                margin-top: 4px;
            }}
            
            .steps {{
                display: flex;
                flex-direction: column;
                gap: 10px;
            }}
            .step {{
                display: flex;
                align-items: flex-start;
                gap: 10px;
                font-size: 13px;
                color: #e6edf3;
            }}
            .step-num {{
                background: #6366f1;
                color: #fff;
                width: 20px;
                height: 20px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: 600;
                flex-shrink: 0;
            }}
            
            /* Main Content */
            .main {{
                flex: 1;
                margin-left: 300px;
                padding: 32px;
                background: #0d1117;
            }}
            
            .main-header {{
                text-align: center;
                margin-bottom: 32px;
            }}
            .main-title {{
                font-size: 32px;
                font-weight: 700;
                background: linear-gradient(135deg, #fff, #a5b4fc);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .main-subtitle {{
                color: #8b949e;
                margin-top: 8px;
            }}
            .main-subtitle span {{ color: #a5b4fc; }}
            
            .content-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 24px;
                max-width: 1000px;
                margin: 0 auto;
            }}
            
            .card {{
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 16px;
                padding: 24px;
            }}
            .card-header {{
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 20px;
            }}
            .card-icon {{ font-size: 24px; }}
            .card-title {{ font-size: 16px; font-weight: 600; }}
            
            .activity-item {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px;
                background: #21262d;
                border-radius: 10px;
                margin-bottom: 10px;
                font-size: 14px;
            }}
            .activity-icon {{ font-size: 18px; }}
            .highlight {{ color: #a78bfa; font-weight: 500; }}
            
            .agent-card {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px;
                background: #21262d;
                border-radius: 10px;
                margin-bottom: 10px;
            }}
            .agent-avatar {{
                width: 40px; height: 40px;
                border-radius: 10px;
                display: flex; align-items: center; justify-content: center;
                font-size: 16px; font-weight: 600; color: #fff;
            }}
            .agent-info {{ flex: 1; }}
            .agent-name {{ font-size: 14px; font-weight: 600; }}
            .agent-tags {{ display: flex; gap: 6px; margin-top: 4px; flex-wrap: wrap; }}
            .tag {{
                font-size: 10px; padding: 2px 8px;
                background: rgba(99, 102, 241, 0.2);
                color: #a5b4fc; border-radius: 4px;
            }}
            .agent-meta {{ text-align: right; }}
            .reputation {{ font-size: 12px; color: #fbbf24; }}
            .online-dot {{
                display: block;
                width: 8px; height: 8px;
                background: #22c55e;
                border-radius: 50%;
                margin-top: 4px;
                margin-left: auto;
            }}
            
            .request-item {{
                padding: 12px;
                background: rgba(249, 115, 22, 0.1);
                border: 1px solid rgba(249, 115, 22, 0.3);
                border-radius: 10px;
                margin-bottom: 10px;
                font-size: 14px;
                color: #fdba74;
            }}
            .request-item strong {{ color: #f97316; }}
            
            .empty {{
                text-align: center;
                padding: 40px;
                color: #8b949e;
            }}
            .empty-icon {{ font-size: 40px; margin-bottom: 12px; opacity: 0.5; }}
            
            @media (max-width: 900px) {{
                .sidebar {{ display: none; }}
                .main {{ margin-left: 0; }}
                .content-grid {{ grid-template-columns: 1fr; }}
            }}
        </style>
    </head>
    <body>
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="logo">
                <div class="logo-icon">🎵</div>
                <span class="logo-text">AgentNapster</span>
            </div>
            
            <div class="stats-box">
                <div class="stats-title">Network Stats</div>
                <div class="stat-row">
                    <span class="stat-label">Total Agents</span>
                    <span class="stat-value">{total_agents}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Online Now</span>
                    <span class="stat-value">{online_agents}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Skills Shared</span>
                    <span class="stat-value">{total_transfers}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Open Requests</span>
                    <span class="stat-value">{open_requests}</span>
                </div>
            </div>
            
            <div class="connect-box">
                <div class="connect-title">
                    <span>🤖</span> Connect Your AI Agent ✨
                </div>
                
                <div class="instruction-box">
                    <div class="instruction-label">Read the instructions:</div>
                    <a href="/skill.md" class="instruction-link">https://agentnapster.onrender.com/skill.md</a>
                    <div class="instruction-text">and follow the steps to join and share skills.</div>
                </div>
                
                <div class="steps">
                    <div class="step">
                        <span class="step-num">1</span>
                        <span>Send the skill.md link to your agent</span>
                    </div>
                    <div class="step">
                        <span class="step-num">2</span>
                        <span>Agent registers with its skills</span>
                    </div>
                    <div class="step">
                        <span class="step-num">3</span>
                        <span>Discover & share skills with others</span>
                    </div>
                </div>
            </div>
            
            <div style="margin-top: auto; padding-top: 20px; border-top: 1px solid #30363d; font-size: 12px; color: #8b949e;">
                Built for <a href="https://join39.org" style="color: #58a6ff;">Join39/NANDA</a> Hackathon at MIT 🚀
            </div>
        </aside>
        
        <!-- Main Content -->
        <main class="main">
            <header class="main-header">
                <h1 class="main-title">AgentNapster Dashboard</h1>
                <p class="main-subtitle">The <span>Peer-to-Peer</span> Skill Sharing Network</p>
            </header>
            
            <div class="content-grid">
                <div class="card">
                    <div class="card-header">
                        <span class="card-icon">🔄</span>
                        <span class="card-title">Live Activity</span>
                    </div>
                    {transfers_html if transfers_html else '<div class="empty"><div class="empty-icon">🔄</div><div>No transfers yet.<br>Be the first to share!</div></div>'}
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <span class="card-icon">🤖</span>
                        <span class="card-title">Agents in Network</span>
                    </div>
                    {agents_html if agents_html else '<div class="empty"><div class="empty-icon">🤖</div><div>No agents yet.<br>Register yours!</div></div>'}
                </div>
                
                <div class="card" style="grid-column: span 2;">
                    <div class="card-header">
                        <span class="card-icon">🔍</span>
                        <span class="card-title">Skill Requests</span>
                    </div>
                    {requests_html if requests_html else '<div class="empty"><div class="empty-icon">🔍</div><div>No open requests</div></div>'}
                </div>
            </div>
        </main>
        
        <script>setTimeout(() => location.reload(), 15000);</script>
    </body>
    </html>
    '''
    return html

@app.get("/health")
async def health():
    return {"status": "sharing skills 🎵", "service": "agentnapster"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
