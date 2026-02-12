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
    
    # Agents table
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
    
    # Skills registry
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
    
    # Skill transfers (the "sharing" history)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER,
            from_agent_id TEXT,
            to_agent_id TEXT,
            status TEXT,
            timestamp TEXT
        )
    """)
    
    # Skill requests
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
    
    # Ratings/Reviews
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER,
            rater_agent_id TEXT,
            rating INTEGER,
            review TEXT,
            created_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ============================================
# SKILL CATEGORIES
# ============================================

SKILL_CATEGORIES = [
    "utilities",      # weather, time, calculator
    "productivity",   # email, calendar, notes
    "data",          # search, database, analytics
    "finance",       # stocks, crypto, banking
    "social",        # messaging, social media
    "creative",      # image gen, writing, music
    "development",   # code, git, deployment
    "communication", # translate, summarize
    "security",      # audit, permissions, auth
    "other"
]

# ============================================
# AGENT ENDPOINTS
# ============================================

@app.post("/api/agents/register")
async def register_agent(request: Request):
    """
    Register a new agent in the network.
    Body: { "agent_id": "...", "name": "...", "description": "...", "skills": ["skill1", "skill2"] }
    """
    body = await request.json()
    agent_id = body.get("agent_id")
    name = body.get("name", f"Agent-{agent_id[:8]}")
    description = body.get("description", "")
    skills = body.get("skills", [])
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    # Check if agent exists
    existing = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,)).fetchone()
    
    if existing:
        # Update existing agent
        conn.execute("""
            UPDATE agents SET name=?, description=?, skills=?, last_seen=?, status='online'
            WHERE id=?
        """, (name, description, json.dumps(skills), now, agent_id))
    else:
        # Insert new agent
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


@app.get("/api/agents")
async def list_agents(status: str = None):
    """List all agents in the network."""
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    
    if status:
        agents = conn.execute("SELECT * FROM agents WHERE status = ? ORDER BY reputation DESC", (status,)).fetchall()
    else:
        agents = conn.execute("SELECT * FROM agents ORDER BY reputation DESC").fetchall()
    
    conn.close()
    
    return {
        "total_agents": len(agents),
        "agents": [{
            "id": a["id"],
            "name": a["name"],
            "description": a["description"],
            "skills": json.loads(a["skills"]) if a["skills"] else [],
            "reputation": a["reputation"],
            "total_shares": a["total_shares"],
            "status": a["status"]
        } for a in agents]
    }


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get details of a specific agent."""
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    conn.close()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "id": agent["id"],
        "name": agent["name"],
        "description": agent["description"],
        "skills": json.loads(agent["skills"]) if agent["skills"] else [],
        "reputation": agent["reputation"],
        "total_shares": agent["total_shares"],
        "total_receives": agent["total_receives"],
        "registered_at": agent["registered_at"],
        "status": agent["status"]
    }


# ============================================
# SKILL ENDPOINTS
# ============================================

@app.post("/api/skills/publish")
async def publish_skill(request: Request):
    """
    Publish a skill to the network.
    Body: { "agent_id": "...", "skill_name": "...", "category": "...", "description": "...", "endpoint": "...", "parameters": {...} }
    """
    body = await request.json()
    agent_id = body.get("agent_id")
    skill_name = body.get("skill_name")
    category = body.get("category", "other")
    description = body.get("description", "")
    endpoint = body.get("endpoint", "")
    parameters = body.get("parameters", {})
    
    if not agent_id or not skill_name:
        raise HTTPException(status_code=400, detail="agent_id and skill_name are required")
    
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    conn.execute("""
        INSERT INTO skills (skill_name, category, description, owner_agent_id, endpoint, parameters, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (skill_name, category, description, agent_id, endpoint, json.dumps(parameters), now))
    
    skill_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "skill_id": skill_id,
        "message": f"Skill '{skill_name}' published to the network! 🎵"
    }


@app.get("/api/skills")
async def list_skills(category: str = None, search: str = None):
    """List all skills available in the network."""
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    
    query = "SELECT s.*, a.name as owner_name FROM skills s LEFT JOIN agents a ON s.owner_agent_id = a.id WHERE 1=1"
    params = []
    
    if category:
        query += " AND s.category = ?"
        params.append(category)
    
    if search:
        query += " AND (s.skill_name LIKE ? OR s.description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    
    query += " ORDER BY s.times_shared DESC, s.rating DESC"
    
    skills = conn.execute(query, params).fetchall()
    conn.close()
    
    return {
        "total_skills": len(skills),
        "skills": [{
            "id": s["id"],
            "name": s["skill_name"],
            "category": s["category"],
            "description": s["description"],
            "owner_agent_id": s["owner_agent_id"],
            "owner_name": s["owner_name"],
            "endpoint": s["endpoint"],
            "rating": s["rating"],
            "times_shared": s["times_shared"]
        } for s in skills]
    }


@app.get("/api/skills/categories")
async def get_categories():
    """Get all skill categories."""
    return {"categories": SKILL_CATEGORIES}


# ============================================
# P2P DISCOVERY & SHARING
# ============================================

@app.post("/api/discover")
async def discover_skills(request: Request):
    """
    Discover agents who have specific skills.
    Body: { "skills_needed": ["weather", "translate"], "agent_id": "..." }
    """
    body = await request.json()
    skills_needed = body.get("skills_needed", [])
    requester_id = body.get("agent_id", "anonymous")
    
    if not skills_needed:
        raise HTTPException(status_code=400, detail="skills_needed array is required")
    
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    
    # Find agents who have these skills
    results = []
    for skill in skills_needed:
        agents = conn.execute("""
            SELECT * FROM agents 
            WHERE skills LIKE ? AND status = 'online' AND id != ?
            ORDER BY reputation DESC
        """, (f'%"{skill}"%', requester_id)).fetchall()
        
        for agent in agents:
            agent_skills = json.loads(agent["skills"]) if agent["skills"] else []
            if skill.lower() in [s.lower() for s in agent_skills]:
                results.append({
                    "skill": skill,
                    "agent_id": agent["id"],
                    "agent_name": agent["name"],
                    "reputation": agent["reputation"],
                    "total_shares": agent["total_shares"]
                })
    
    conn.close()
    
    return {
        "query": skills_needed,
        "found": len(results),
        "matches": results
    }


@app.post("/api/request")
async def request_skill(request: Request):
    """
    Request a skill from the network.
    Body: { "agent_id": "...", "skill_name": "..." }
    """
    body = await request.json()
    agent_id = body.get("agent_id")
    skill_name = body.get("skill_name")
    
    if not agent_id or not skill_name:
        raise HTTPException(status_code=400, detail="agent_id and skill_name are required")
    
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    conn.execute("""
        INSERT INTO requests (requester_agent_id, skill_name, created_at)
        VALUES (?, ?, ?)
    """, (agent_id, skill_name, now))
    
    request_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "request_id": request_id,
        "message": f"Request for '{skill_name}' posted to the network! Waiting for a peer... 🎵"
    }


@app.post("/api/share")
async def share_skill(request: Request):
    """
    Share a skill with another agent (fulfill a request or direct share).
    Body: { "from_agent_id": "...", "to_agent_id": "...", "skill_name": "...", "request_id": ... (optional) }
    """
    body = await request.json()
    from_agent_id = body.get("from_agent_id")
    to_agent_id = body.get("to_agent_id")
    skill_name = body.get("skill_name")
    request_id = body.get("request_id")
    
    if not from_agent_id or not to_agent_id or not skill_name:
        raise HTTPException(status_code=400, detail="from_agent_id, to_agent_id, and skill_name are required")
    
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    # Find the skill
    skill = conn.execute("SELECT id FROM skills WHERE skill_name = ? AND owner_agent_id = ?", 
                         (skill_name, from_agent_id)).fetchone()
    
    skill_id = skill[0] if skill else None
    
    # Record the transfer
    conn.execute("""
        INSERT INTO transfers (skill_id, from_agent_id, to_agent_id, status, timestamp)
        VALUES (?, ?, ?, 'completed', ?)
    """, (skill_id, from_agent_id, to_agent_id, now))
    
    # Update agent stats
    conn.execute("UPDATE agents SET total_shares = total_shares + 1 WHERE id = ?", (from_agent_id,))
    conn.execute("UPDATE agents SET total_receives = total_receives + 1 WHERE id = ?", (to_agent_id,))
    
    # Update skill stats
    if skill_id:
        conn.execute("UPDATE skills SET times_shared = times_shared + 1 WHERE id = ?", (skill_id,))
    
    # Fulfill request if provided
    if request_id:
        conn.execute("""
            UPDATE requests SET status = 'fulfilled', fulfilled_by = ?, fulfilled_at = ?
            WHERE id = ?
        """, (from_agent_id, now, request_id))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": f"Skill '{skill_name}' shared from {from_agent_id} to {to_agent_id}! 🎵",
        "transfer": {
            "skill": skill_name,
            "from": from_agent_id,
            "to": to_agent_id,
            "timestamp": now
        }
    }


@app.get("/api/requests")
async def list_requests(status: str = "open"):
    """List skill requests in the network."""
    conn = sqlite3.connect("agentnapster.db")
    conn.row_factory = sqlite3.Row
    
    requests = conn.execute("""
        SELECT r.*, a.name as requester_name 
        FROM requests r 
        LEFT JOIN agents a ON r.requester_agent_id = a.id
        WHERE r.status = ?
        ORDER BY r.created_at DESC
    """, (status,)).fetchall()
    
    conn.close()
    
    return {
        "total_requests": len(requests),
        "requests": [{
            "id": r["id"],
            "skill_name": r["skill_name"],
            "requester_id": r["requester_agent_id"],
            "requester_name": r["requester_name"],
            "status": r["status"],
            "created_at": r["created_at"]
        } for r in requests]
    }


# ============================================
# REPUTATION & RATINGS
# ============================================

@app.post("/api/rate")
async def rate_skill(request: Request):
    """
    Rate a skill after receiving it.
    Body: { "agent_id": "...", "skill_id": ..., "rating": 1-5, "review": "..." }
    """
    body = await request.json()
    agent_id = body.get("agent_id")
    skill_id = body.get("skill_id")
    rating = body.get("rating", 5)
    review = body.get("review", "")
    
    if not agent_id or not skill_id:
        raise HTTPException(status_code=400, detail="agent_id and skill_id are required")
    
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="rating must be between 1 and 5")
    
    conn = sqlite3.connect("agentnapster.db")
    now = datetime.now().isoformat()
    
    conn.execute("""
        INSERT INTO ratings (skill_id, rater_agent_id, rating, review, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (skill_id, agent_id, rating, review, now))
    
    # Update skill average rating
    avg = conn.execute("SELECT AVG(rating) FROM ratings WHERE skill_id = ?", (skill_id,)).fetchone()[0]
    conn.execute("UPDATE skills SET rating = ? WHERE id = ?", (avg, skill_id))
    
    # Update owner reputation
    skill = conn.execute("SELECT owner_agent_id FROM skills WHERE id = ?", (skill_id,)).fetchone()
    if skill:
        owner_avg = conn.execute("""
            SELECT AVG(r.rating) FROM ratings r 
            JOIN skills s ON r.skill_id = s.id 
            WHERE s.owner_agent_id = ?
        """, (skill[0],)).fetchone()[0]
        if owner_avg:
            conn.execute("UPDATE agents SET reputation = ? WHERE id = ?", (owner_avg, skill[0]))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": "Thanks for rating! This helps the network. 🎵"
    }


# ============================================
# NETWORK STATS
# ============================================

@app.get("/api/stats")
async def network_stats():
    """Get network-wide statistics."""
    conn = sqlite3.connect("agentnapster.db")
    
    total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    online_agents = conn.execute("SELECT COUNT(*) FROM agents WHERE status = 'online'").fetchone()[0]
    total_skills = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    total_transfers = conn.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
    open_requests = conn.execute("SELECT COUNT(*) FROM requests WHERE status = 'open'").fetchone()[0]
    
    # Top skills
    top_skills = conn.execute("""
        SELECT skill_name, times_shared FROM skills ORDER BY times_shared DESC LIMIT 5
    """).fetchall()
    
    # Top sharers
    top_sharers = conn.execute("""
        SELECT name, total_shares, reputation FROM agents ORDER BY total_shares DESC LIMIT 5
    """).fetchall()
    
    conn.close()
    
    return {
        "network": {
            "total_agents": total_agents,
            "online_agents": online_agents,
            "total_skills": total_skills,
            "total_transfers": total_transfers,
            "open_requests": open_requests
        },
        "top_skills": [{"name": s[0], "shares": s[1]} for s in top_skills],
        "top_sharers": [{"name": s[0], "shares": s[1], "reputation": s[2]} for s in top_sharers]
    }


# ============================================
# JOIN39 INTEGRATION ENDPOINT
# ============================================

@app.post("/api/napster")
async def napster_action(request: Request):
    """
    Main endpoint for Join39 integration.
    Actions: register, discover, request, share, list_skills, list_agents, stats
    """
    body = await request.json()
    action = body.get("action", "").lower()
    params = body.get("params", {})
    
    if action == "register":
        return await register_agent(request)
    
    elif action == "discover":
        skills_needed = params.get("skills_needed", [])
        agent_id = params.get("agent_id", "anonymous")
        
        conn = sqlite3.connect("agentnapster.db")
        conn.row_factory = sqlite3.Row
        
        results = []
        for skill in skills_needed:
            agents = conn.execute("""
                SELECT * FROM agents WHERE skills LIKE ? AND status = 'online'
                ORDER BY reputation DESC LIMIT 5
            """, (f'%{skill}%',)).fetchall()
            
            for agent in agents:
                results.append({
                    "skill": skill,
                    "agent_id": agent["id"],
                    "agent_name": agent["name"],
                    "reputation": agent["reputation"]
                })
        
        conn.close()
        return {"found": len(results), "matches": results}
    
    elif action == "request":
        return await request_skill(request)
    
    elif action == "share":
        return await share_skill(request)
    
    elif action == "list_skills":
        category = params.get("category")
        conn = sqlite3.connect("agentnapster.db")
        conn.row_factory = sqlite3.Row
        
        if category:
            skills = conn.execute("SELECT * FROM skills WHERE category = ?", (category,)).fetchall()
        else:
            skills = conn.execute("SELECT * FROM skills ORDER BY times_shared DESC LIMIT 20").fetchall()
        
        conn.close()
        return {"skills": [{"name": s["skill_name"], "category": s["category"], "rating": s["rating"]} for s in skills]}
    
    elif action == "list_agents":
        conn = sqlite3.connect("agentnapster.db")
        conn.row_factory = sqlite3.Row
        agents = conn.execute("SELECT * FROM agents WHERE status = 'online' ORDER BY reputation DESC LIMIT 20").fetchall()
        conn.close()
        return {"agents": [{"id": a["id"], "name": a["name"], "reputation": a["reputation"]} for a in agents]}
    
    elif action == "stats":
        return await network_stats()
    
    else:
        return {
            "error": f"Unknown action: {action}",
            "available_actions": ["register", "discover", "request", "share", "list_skills", "list_agents", "stats"]
        }


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
    
    # Recent transfers
    conn.row_factory = sqlite3.Row
    recent_transfers = conn.execute("""
        SELECT t.*, s.skill_name, 
               a1.name as from_name, a2.name as to_name
        FROM transfers t
        LEFT JOIN skills s ON t.skill_id = s.id
        LEFT JOIN agents a1 ON t.from_agent_id = a1.id
        LEFT JOIN agents a2 ON t.to_agent_id = a2.id
        ORDER BY t.timestamp DESC LIMIT 10
    """).fetchall()
    
    # Online agents
    agents = conn.execute("SELECT * FROM agents ORDER BY reputation DESC LIMIT 10").fetchall()
    
    # Available skills
    skills = conn.execute("SELECT * FROM skills ORDER BY times_shared DESC LIMIT 10").fetchall()
    
    # Open requests
    requests = conn.execute("""
        SELECT r.*, a.name as requester_name 
        FROM requests r 
        LEFT JOIN agents a ON r.requester_agent_id = a.id
        WHERE r.status = 'open'
        ORDER BY r.created_at DESC LIMIT 5
    """).fetchall()
    
    conn.close()
    
    # Build transfers HTML
    transfers_html = ""
    for t in recent_transfers:
        transfers_html += f"""
        <div class="transfer-item">
            <span class="transfer-icon">🔄</span>
            <span><strong>{t['from_name'] or t['from_agent_id'][:8]}</strong> shared 
            <span class="skill-tag">{t['skill_name'] or 'skill'}</span> with 
            <strong>{t['to_name'] or t['to_agent_id'][:8]}</strong></span>
        </div>
        """
    
    # Build agents HTML
    agents_html = ""
    for a in agents:
        skills_list = json.loads(a["skills"]) if a["skills"] else []
        skills_tags = "".join([f'<span class="skill-tag-small">{s}</span>' for s in skills_list[:3]])
        status_color = "#4ade80" if a["status"] == "online" else "#888"
        agents_html += f"""
        <div class="agent-card">
            <div class="agent-header">
                <span class="agent-name">{a['name']}</span>
                <span class="agent-status" style="color: {status_color}">●</span>
            </div>
            <div class="agent-skills">{skills_tags}</div>
            <div class="agent-stats">
                ⭐ {a['reputation']:.1f} · 📤 {a['total_shares']} shared
            </div>
        </div>
        """
    
    # Build skills HTML
    skills_html = ""
    for s in skills:
        skills_html += f"""
        <div class="skill-card">
            <div class="skill-name">{s['skill_name']}</div>
            <div class="skill-meta">{s['category']} · ⭐ {s['rating']:.1f} · 📤 {s['times_shared']}x shared</div>
        </div>
        """
    
    # Build requests HTML
    requests_html = ""
    for r in requests:
        requests_html += f"""
        <div class="request-item">
            <span class="request-skill">🔍 {r['skill_name']}</span>
            <span class="request-by">requested by {r['requester_name'] or r['requester_agent_id'][:8]}</span>
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AgentNapster 🎵 - P2P Skill Sharing</title>
        <meta http-equiv="refresh" content="10">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%);
                min-height: 100vh;
                color: #e5e5e5;
                padding: 40px;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            
            h1 {{ 
                font-size: 2.5rem;
                text-align: center;
                margin-bottom: 8px;
                background: linear-gradient(90deg, #00d9ff, #00ff88, #00d9ff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .subtitle {{
                text-align: center;
                color: #888;
                margin-bottom: 40px;
                font-size: 1.1rem;
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 16px;
                margin-bottom: 40px;
            }}
            .stat-card {{
                background: rgba(0, 217, 255, 0.1);
                border: 1px solid rgba(0, 217, 255, 0.3);
                border-radius: 12px;
                padding: 20px;
                text-align: center;
            }}
            .stat-value {{
                font-size: 2rem;
                font-weight: bold;
                color: #00d9ff;
            }}
            .stat-label {{
                color: #888;
                font-size: 0.85rem;
                margin-top: 4px;
            }}
            
            .main-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 24px;
            }}
            
            .section {{
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 16px;
                padding: 24px;
            }}
            .section h2 {{
                color: #00ff88;
                font-size: 1.2rem;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .transfer-item {{
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 12px;
                background: rgba(0, 217, 255, 0.05);
                border-radius: 8px;
                margin-bottom: 8px;
                font-size: 0.9rem;
            }}
            .transfer-icon {{ font-size: 1.2rem; }}
            
            .skill-tag {{
                background: rgba(0, 255, 136, 0.2);
                color: #00ff88;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 0.85rem;
            }}
            .skill-tag-small {{
                background: rgba(0, 217, 255, 0.2);
                color: #00d9ff;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 0.75rem;
                margin-right: 4px;
            }}
            
            .agent-card {{
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 10px;
                padding: 14px;
                margin-bottom: 10px;
            }}
            .agent-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .agent-name {{ font-weight: 600; color: #fff; }}
            .agent-skills {{ margin: 8px 0; }}
            .agent-stats {{ color: #888; font-size: 0.85rem; }}
            
            .skill-card {{
                background: rgba(0, 255, 136, 0.05);
                border: 1px solid rgba(0, 255, 136, 0.2);
                border-radius: 10px;
                padding: 14px;
                margin-bottom: 10px;
            }}
            .skill-name {{ font-weight: 600; color: #00ff88; }}
            .skill-meta {{ color: #888; font-size: 0.85rem; margin-top: 4px; }}
            
            .request-item {{
                display: flex;
                justify-content: space-between;
                padding: 12px;
                background: rgba(255, 200, 0, 0.05);
                border: 1px solid rgba(255, 200, 0, 0.2);
                border-radius: 8px;
                margin-bottom: 8px;
            }}
            .request-skill {{ color: #ffc800; font-weight: 500; }}
            .request-by {{ color: #888; font-size: 0.85rem; }}
            
            .empty {{ color: #666; text-align: center; padding: 20px; }}
            
            .api-info {{
                background: rgba(0, 217, 255, 0.1);
                border: 1px solid rgba(0, 217, 255, 0.3);
                border-radius: 12px;
                padding: 20px;
                margin-top: 30px;
            }}
            .api-info h3 {{ color: #00d9ff; margin-bottom: 12px; }}
            .api-info code {{
                background: rgba(0,0,0,0.3);
                padding: 8px 12px;
                border-radius: 6px;
                display: block;
                margin: 8px 0;
                font-size: 0.85rem;
                color: #00ff88;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎵 AgentNapster</h1>
            <p class="subtitle">Peer-to-Peer Skill Sharing Network for AI Agents</p>
            
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
                    <div class="stat-label">Skills Available</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_transfers}</div>
                    <div class="stat-label">Total Shares</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{open_requests}</div>
                    <div class="stat-label">Open Requests</div>
                </div>
            </div>
            
            <div class="main-grid">
                <div class="section">
                    <h2>🔄 Live Transfers</h2>
                    {transfers_html if transfers_html else '<div class="empty">No transfers yet. Be the first to share!</div>'}
                </div>
                
                <div class="section">
                    <h2>🤖 Agents in Network</h2>
                    {agents_html if agents_html else '<div class="empty">No agents yet. Register yours!</div>'}
                </div>
                
                <div class="section">
                    <h2>🛠️ Available Skills</h2>
                    {skills_html if skills_html else '<div class="empty">No skills published yet.</div>'}
                    
                    <h2 style="margin-top: 24px;">🔍 Open Requests</h2>
                    {requests_html if requests_html else '<div class="empty">No open requests.</div>'}
                </div>
            </div>
            
            <div class="api-info">
                <h3>🔌 API Endpoint for Join39</h3>
                <p>POST /api/napster</p>
                <code>{{"action": "discover", "params": {{"skills_needed": ["weather", "translate"]}}}}</code>
                <code>{{"action": "register", "params": {{"agent_id": "...", "name": "...", "skills": ["..."]}}}}</code>
                <code>{{"action": "share", "params": {{"from_agent_id": "...", "to_agent_id": "...", "skill_name": "..."}}}}</code>
            </div>
        </div>
    </body>
    </html>
    """
    return html


@app.get("/health")
async def health():
    return {"status": "sharing skills 🎵", "service": "agentnapster"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
