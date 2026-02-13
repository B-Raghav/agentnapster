from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import sqlite3
import json
import hashlib

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
# AGENT REGISTRATION (Works for both App & Experience)
# ============================================

@app.post("/api/agents/register")
async def register_agent(request: Request):
    """Register an agent - works for both direct API and Join39 Experience"""
    body = await request.json()
    
    # Support both formats
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
        conn.execute("""
            UPDATE agents SET name=?, description=?, skills=?, last_seen=?, status='online'
            WHERE id=?
        """, (name, description, json.dumps(skills), now, agent_id))
    else:
        conn.execute("""
            INSERT INTO agents (id, name, description, skills, registered_at, last_seen, status)
            VALUES (?, ?, ?, ?, ?, ?, 'online')
        """, (agent_id, name, description, json.dumps(skills), now, now))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "agent_id": agent_id,
        "message": f"Welcome to AgentNapster, {name}! 🎵",
        "skills_registered": skills
    }

@app.post("/api/agents/deregister")
async def deregister_agent(request: Request):
    """Remove an agent from the network"""
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
    """List all agents in the network"""
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    agents = conn.execute("SELECT * FROM agents ORDER BY reputation DESC").fetchall()
    conn.close()
    
    return {
        "total_agents": len(agents),
        "agents": [{
            "id": a["id"],
            "name": a["name"],
            "skills": json.loads(a["skills"]) if a["skills"] else [],
            "reputation": a["reputation"],
            "total_shares": a["total_shares"],
            "status": a["status"]
        } for a in agents]
    }

# ============================================
# SKILL SHARING
# ============================================

@app.post("/api/skills/share")
async def share_skill(request: Request):
    """Share a skill between agents"""
    body = await request.json()
    from_agent = body.get("from_agent_id")
    to_agent = body.get("to_agent_id")
    skill_name = body.get("skill_name")
    
    if not all([from_agent, to_agent, skill_name]):
        raise HTTPException(status_code=400, detail="from_agent_id, to_agent_id, and skill_name required")
    
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    conn.execute("""
        INSERT INTO transfers (skill_name, from_agent_id, to_agent_id, status, timestamp)
        VALUES (?, ?, ?, 'completed', ?)
    """, (skill_name, from_agent, to_agent, now))
    
    conn.execute("UPDATE agents SET total_shares = total_shares + 1 WHERE id = ?", (from_agent,))
    conn.execute("UPDATE agents SET total_receives = total_receives + 1 WHERE id = ?", (to_agent,))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": f"Skill '{skill_name}' shared from {from_agent} to {to_agent}! 🎵"
    }

@app.post("/api/skills/request")
async def request_skill(request: Request):
    """Request a skill from the network"""
    body = await request.json()
    agent_id = body.get("agent_id")
    skill_name = body.get("skill_name")
    
    if not all([agent_id, skill_name]):
        raise HTTPException(status_code=400, detail="agent_id and skill_name required")
    
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    conn.execute("""
        INSERT INTO requests (requester_agent_id, skill_name, created_at)
        VALUES (?, ?, ?)
    """, (agent_id, skill_name, now))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": f"Request for '{skill_name}' posted! 🎵"
    }

@app.post("/api/skills/discover")
async def discover_skills(request: Request):
    """Find agents with specific skills"""
    body = await request.json()
    skills_needed = body.get("skills_needed", [])
    
    if not skills_needed:
        raise HTTPException(status_code=400, detail="skills_needed array required")
    
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    
    results = []
    for skill in skills_needed:
        agents = conn.execute("""
            SELECT * FROM agents WHERE skills LIKE ? AND status = 'online'
        """, (f'%{skill}%',)).fetchall()
        
        for a in agents:
            results.append({
                "skill": skill,
                "agent_id": a["id"],
                "agent_name": a["name"],
                "reputation": a["reputation"]
            })
    
    conn.close()
    return {"found": len(results), "matches": results}

# ============================================
# MAIN JOIN39 ENDPOINT
# ============================================

@app.post("/api/napster")
async def napster_action(request: Request):
    """Main endpoint for Join39 - handles all actions"""
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
        
        elif action == "list_skills":
            conn.row_factory = sqlite3.Row
            skills = conn.execute("SELECT * FROM skills ORDER BY times_shared DESC LIMIT 20").fetchall()
            return {"skills": [{"name": s["skill_name"], "category": s["category"]} for s in skills]}
        
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
# DASHBOARD
# ============================================

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    conn = sqlite3.connect("agentnapster.db")
    
    total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    online_agents = conn.execute("SELECT COUNT(*) FROM agents WHERE status = 'online'").fetchone()[0]
    total_skills = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    total_transfers = conn.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
    open_requests = conn.execute("SELECT COUNT(*) FROM requests WHERE status = 'open'").fetchone()[0]
    
    conn.row_factory = sqlite3.Row
    recent_transfers = conn.execute("""
        SELECT * FROM transfers ORDER BY timestamp DESC LIMIT 10
    """).fetchall()
    
    agents = conn.execute("SELECT * FROM agents ORDER BY reputation DESC LIMIT 10").fetchall()
    requests = conn.execute("SELECT * FROM requests WHERE status = 'open' ORDER BY created_at DESC LIMIT 5").fetchall()
    
    conn.close()
    
    # Build HTML
    transfers_html = ""
    for t in recent_transfers:
        transfers_html += f'''
        <div class="activity-item">
            <div class="activity-icon">↔️</div>
            <div class="activity-content">
                <span class="activity-text"><strong>{t['from_agent_id'][:12]}</strong> shared <span class="highlight">{t['skill_name']}</span> with <strong>{t['to_agent_id'][:12]}</strong></span>
            </div>
        </div>
        '''
    
    agents_html = ""
    colors = ["#6366f1", "#8b5cf6", "#ec4899", "#f43f5e", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#06b6d4", "#3b82f6"]
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
    
    requests_html = ""
    for r in requests:
        requests_html += f'''
        <div class="request-item">
            <span class="request-icon">🔍</span>
            <span class="request-text">Looking for <strong>{r['skill_name']}</strong></span>
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
                background: #0f0f13;
                min-height: 100vh;
                color: #e4e4e7;
            }}
            .bg-gradient {{
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: 
                    radial-gradient(ellipse at 20% 20%, rgba(99, 102, 241, 0.15) 0%, transparent 50%),
                    radial-gradient(ellipse at 80% 80%, rgba(139, 92, 246, 0.15) 0%, transparent 50%);
                z-index: -1;
            }}
            .container {{ max-width: 1400px; margin: 0 auto; padding: 40px 24px; }}
            .header {{ text-align: center; margin-bottom: 48px; }}
            .logo {{ display: inline-flex; align-items: center; gap: 16px; margin-bottom: 16px; }}
            .logo-icon {{
                width: 64px; height: 64px;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                border-radius: 20px;
                display: flex; align-items: center; justify-content: center;
                font-size: 32px;
                box-shadow: 0 20px 40px rgba(99, 102, 241, 0.3);
            }}
            .logo-text {{
                font-size: 42px; font-weight: 700;
                background: linear-gradient(135deg, #fff, #a5b4fc);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .tagline {{ font-size: 18px; color: #71717a; }}
            .tagline span {{ color: #a5b4fc; font-weight: 500; }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 16px;
                margin-bottom: 40px;
            }}
            .stat-card {{
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 20px;
                padding: 24px;
                text-align: center;
                transition: all 0.3s;
            }}
            .stat-card:hover {{
                transform: translateY(-4px);
                border-color: rgba(99, 102, 241, 0.3);
            }}
            .stat-value {{
                font-size: 36px; font-weight: 700;
                background: linear-gradient(135deg, #fff, #6366f1);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .stat-label {{ font-size: 13px; color: #71717a; text-transform: uppercase; }}
            
            .main-grid {{
                display: grid;
                grid-template-columns: 1fr 1.2fr 1fr;
                gap: 24px;
            }}
            .card {{
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 24px;
                padding: 28px;
            }}
            .card-header {{
                display: flex; align-items: center; gap: 12px;
                margin-bottom: 24px;
            }}
            .card-icon {{
                width: 40px; height: 40px;
                border-radius: 12px;
                display: flex; align-items: center; justify-content: center;
                font-size: 20px;
                background: rgba(99, 102, 241, 0.2);
            }}
            .card-title {{ font-size: 16px; font-weight: 600; color: #fff; }}
            
            .activity-item {{
                display: flex; align-items: center; gap: 14px;
                padding: 14px;
                background: rgba(255,255,255,0.02);
                border-radius: 14px;
                margin-bottom: 10px;
            }}
            .activity-icon {{
                width: 36px; height: 36px;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                border-radius: 10px;
                display: flex; align-items: center; justify-content: center;
            }}
            .activity-text {{ font-size: 14px; color: #a1a1aa; }}
            .activity-text strong {{ color: #fff; }}
            .highlight {{ color: #a78bfa; font-weight: 500; }}
            
            .agent-card {{
                display: flex; align-items: center; gap: 14px;
                padding: 14px;
                background: rgba(255,255,255,0.02);
                border-radius: 14px;
                margin-bottom: 10px;
            }}
            .agent-avatar {{
                width: 44px; height: 44px;
                border-radius: 14px;
                display: flex; align-items: center; justify-content: center;
                font-size: 18px; font-weight: 600; color: #fff;
            }}
            .agent-info {{ flex: 1; }}
            .agent-name {{ font-size: 15px; font-weight: 600; color: #fff; }}
            .agent-tags {{ display: flex; gap: 6px; margin-top: 4px; }}
            .tag {{
                font-size: 11px; padding: 3px 8px;
                background: rgba(99, 102, 241, 0.15);
                color: #a5b4fc; border-radius: 6px;
            }}
            .agent-meta {{ display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }}
            .reputation {{ font-size: 13px; color: #fbbf24; }}
            .online-dot {{
                width: 8px; height: 8px;
                background: #22c55e;
                border-radius: 50%;
                box-shadow: 0 0 8px #22c55e;
            }}
            
            .request-item {{
                display: flex; align-items: center; gap: 12px;
                padding: 12px;
                background: rgba(251, 191, 36, 0.05);
                border: 1px solid rgba(251, 191, 36, 0.15);
                border-radius: 12px;
                margin-bottom: 8px;
            }}
            .request-text {{ font-size: 14px; color: #a1a1aa; }}
            .request-text strong {{ color: #fbbf24; }}
            
            .empty-state {{
                text-align: center; padding: 40px; color: #52525b;
            }}
            .empty-state-icon {{ font-size: 48px; margin-bottom: 16px; opacity: 0.5; }}
            
            .api-section {{
                background: rgba(99, 102, 241, 0.1);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 24px;
                padding: 32px;
                margin-top: 40px;
            }}
            .api-title {{ font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 16px; }}
            .code-block {{
                background: rgba(0,0,0,0.3);
                border-radius: 12px;
                padding: 16px;
                margin-bottom: 10px;
                font-family: monospace;
                font-size: 13px;
                color: #a5b4fc;
            }}
            
            @media (max-width: 1200px) {{
                .stats-grid {{ grid-template-columns: repeat(3, 1fr); }}
                .main-grid {{ grid-template-columns: 1fr; }}
            }}
        </style>
    </head>
    <body>
        <div class="bg-gradient"></div>
        <div class="container">
            <header class="header">
                <div class="logo">
                    <div class="logo-icon">🎵</div>
                    <span class="logo-text">AgentNapster</span>
                </div>
                <p class="tagline">The <span>Peer-to-Peer</span> Skill Sharing Network for AI Agents</p>
            </header>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{total_agents}</div>
                    <div class="stat-label">Total Agents</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{online_agents}</div>
                    <div class="stat-label">Online Now</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_skills}</div>
                    <div class="stat-label">Skills</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_transfers}</div>
                    <div class="stat-label">Total Shares</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{open_requests}</div>
                    <div class="stat-label">Requests</div>
                </div>
            </div>
            
            <div class="main-grid">
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">↔️</div>
                        <span class="card-title">Live Activity</span>
                    </div>
                    {transfers_html if transfers_html else '<div class="empty-state"><div class="empty-state-icon">🔄</div><div>No transfers yet</div></div>'}
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">🤖</div>
                        <span class="card-title">Agents in Network</span>
                    </div>
                    {agents_html if agents_html else '<div class="empty-state"><div class="empty-state-icon">🤖</div><div>No agents yet</div></div>'}
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">🔍</div>
                        <span class="card-title">Skill Requests</span>
                    </div>
                    {requests_html if requests_html else '<div class="empty-state"><div class="empty-state-icon">🔍</div><div>No requests</div></div>'}
                </div>
            </div>
            
            <div class="api-section">
                <div class="api-title">🔌 API for Join39</div>
                <div class="code-block">POST /api/napster</div>
                <div class="code-block">{{"action": "register", "params": {{"agent_id": "...", "name": "...", "skills": [...]}}}}</div>
                <div class="code-block">{{"action": "share", "params": {{"from_agent_id": "...", "to_agent_id": "...", "skill_name": "..."}}}}</div>
            </div>
        </div>
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
