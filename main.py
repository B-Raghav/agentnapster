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
        # Handle register directly
        agent_id = params.get("agent_id")
        name = params.get("name", f"Agent-{agent_id[:8] if agent_id else 'unknown'}")
        description = params.get("description", "")
        skills = params.get("skills", [])
        
        if not agent_id:
            return {"error": "agent_id is required"}
        
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
        # Delegate to register_agent endpoint
        register_request = Request(scope={"type": "http"}, receive=None)
        register_request._json = params # Manually set the json body
        return await register_agent(register_request)
    
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
        # Handle request directly
        agent_id = params.get("agent_id")
        skill_name = params.get("skill_name")
        
        if not agent_id or not skill_name:
            return {"error": "agent_id and skill_name are required"}
        
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
            "message": f"Request for '{skill_name}' posted to the network! 🎵"
        }
    
    elif action == "share":
        # Delegate to share_skill endpoint
        share_request = Request(scope={"type": "http"}, receive=None)
        share_request._json = params # Manually set the json body
        return await share_skill(share_request)
    
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
# DASHBOARD - BEAUTIFUL UI
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
        <div class="activity-item">
            <div class="activity-icon">↔️</div>
            <div class="activity-content">
                <span class="activity-text"><strong>{t['from_name'] or t['from_agent_id'][:8]}</strong> shared <span class="highlight">{t['skill_name'] or 'skill'}</span> with <strong>{t['to_name'] or t['to_agent_id'][:8]}</strong></span>
                <span class="activity-time">just now</span>
            </div>
        </div>
        """
    
    # Build agents HTML
    agents_html = ""
    colors = ["#6366f1", "#8b5cf6", "#ec4899", "#f43f5e", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#06b6d4", "#3b82f6"]
    for i, a in enumerate(agents):
        skills_list = json.loads(a["skills"]) if a["skills"] else []
        skills_tags = "".join([f'<span class="tag">{s}</span>' for s in skills_list[:3]])
        color = colors[i % len(colors)]
        agents_html += f"""
        <div class="agent-card">
            <div class="agent-avatar" style="background: {color}">{a['name'][0].upper()}</div>
            <div class="agent-info">
                <div class="agent-name">{a['name']}</div>
                <div class="agent-tags">{skills_tags}</div>
            </div>
            <div class="agent-meta">
                <span class="reputation">⭐ {a['reputation']:.1f}</span>
                <span class="online-dot"></span>
            </div>
        </div>
        """
    
    # Build skills HTML  
    skills_html = ""
    skill_icons = {"utilities": "🔧", "productivity": "📊", "data": "📁", "finance": "💰", "social": "💬", "creative": "🎨", "development": "💻", "communication": "🌐", "security": "🔒", "other": "📦"}
    for s in skills:
        icon = skill_icons.get(s['category'], "📦")
        skills_html += f"""
        <div class="skill-item">
            <span class="skill-icon">{icon}</span>
            <span class="skill-name">{s['skill_name']}</span>
            <span class="skill-stats">↔️ {s['times_shared']}</span>
        </div>
        """
    
    # Build requests HTML
    requests_html = ""
    for r in requests:
        requests_html += f"""
        <div class="request-item">
            <span class="request-icon">🔍</span>
            <span class="request-text">Looking for <strong>{r['skill_name']}</strong></span>
            <span class="request-by">{r['requester_name'] or 'Anonymous'}</span>
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AgentNapster - P2P Skill Sharing for AI Agents</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{ 
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #0f0f13;
                min-height: 100vh;
                color: #e4e4e7;
                overflow-x: hidden;
            }}
            
            /* Animated background */
            .bg-gradient {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: 
                    radial-gradient(ellipse at 20% 20%, rgba(99, 102, 241, 0.15) 0%, transparent 50%),
                    radial-gradient(ellipse at 80% 80%, rgba(139, 92, 246, 0.15) 0%, transparent 50%),
                    radial-gradient(ellipse at 50% 50%, rgba(14, 165, 233, 0.08) 0%, transparent 70%);
                z-index: -1;
                animation: pulse 8s ease-in-out infinite alternate;
            }}
            
            @keyframes pulse {{
                0% {{ opacity: 0.8; }}
                100% {{ opacity: 1; }}
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 40px 24px;
            }}
            
            /* Header */
            .header {{
                text-align: center;
                margin-bottom: 48px;
            }}
            
            .logo {{
                display: inline-flex;
                align-items: center;
                gap: 16px;
                margin-bottom: 16px;
            }}
            
            .logo-icon {{
                width: 64px;
                height: 64px;
                background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
                border-radius: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 32px;
                box-shadow: 0 20px 40px rgba(99, 102, 241, 0.3);
            }}
            
            .logo-text {{
                font-size: 42px;
                font-weight: 700;
                background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                letter-spacing: -1px;
            }}
            
            .tagline {{
                font-size: 18px;
                color: #71717a;
                font-weight: 400;
            }}
            
            .tagline span {{
                color: #a5b4fc;
                font-weight: 500;
            }}
            
            /* Stats Grid */
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 16px;
                margin-bottom: 40px;
            }}
            
            .stat-card {{
                background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 20px;
                padding: 24px;
                text-align: center;
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
            }}
            
            .stat-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 2px;
                background: linear-gradient(90deg, #6366f1, #8b5cf6, #a855f7);
                opacity: 0;
                transition: opacity 0.3s;
            }}
            
            .stat-card:hover {{
                transform: translateY(-4px);
                border-color: rgba(99, 102, 241, 0.3);
                box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            }}
            
            .stat-card:hover::before {{
                opacity: 1;
            }}
            
            .stat-value {{
                font-size: 36px;
                font-weight: 700;
                background: linear-gradient(135deg, #fff 0%, #6366f1 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 4px;
            }}
            
            .stat-label {{
                font-size: 13px;
                color: #71717a;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            /* Main Layout */
            .main-grid {{
                display: grid;
                grid-template-columns: 1fr 1.2fr 1fr;
                gap: 24px;
                margin-bottom: 40px;
            }}
            
            .card {{
                background: linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 24px;
                padding: 28px;
                backdrop-filter: blur(10px);
            }}
            
            .card-header {{
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 24px;
            }}
            
            .card-icon {{
                width: 40px;
                height: 40px;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 20px;
            }}
            
            .card-icon.purple {{ background: rgba(139, 92, 246, 0.2); }}
            .card-icon.blue {{ background: rgba(59, 130, 246, 0.2); }}
            .card-icon.green {{ background: rgba(34, 197, 94, 0.2); }}
            .card-icon.orange {{ background: rgba(249, 115, 22, 0.2); }}
            
            .card-title {{
                font-size: 16px;
                font-weight: 600;
                color: #fff;
            }}
            
            /* Activity Feed */
            .activity-item {{
                display: flex;
                align-items: center;
                gap: 14px;
                padding: 14px;
                background: rgba(255,255,255,0.02);
                border-radius: 14px;
                margin-bottom: 10px;
                transition: all 0.2s;
            }}
            
            .activity-item:hover {{
                background: rgba(255,255,255,0.05);
            }}
            
            .activity-icon {{
                width: 36px;
                height: 36px;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                border-radius: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 16px;
            }}
            
            .activity-content {{
                flex: 1;
            }}
            
            .activity-text {{
                font-size: 14px;
                color: #a1a1aa;
            }}
            
            .activity-text strong {{
                color: #fff;
                font-weight: 500;
            }}
            
            .highlight {{
                color: #a78bfa;
                font-weight: 500;
            }}
            
            .activity-time {{
                display: block;
                font-size: 12px;
                color: #52525b;
                margin-top: 2px;
            }}
            
            /* Agent Cards */
            .agent-card {{
                display: flex;
                align-items: center;
                gap: 14px;
                padding: 14px;
                background: rgba(255,255,255,0.02);
                border-radius: 14px;
                margin-bottom: 10px;
                transition: all 0.2s;
            }}
            
            .agent-card:hover {{
                background: rgba(255,255,255,0.05);
                transform: translateX(4px);
            }}
            
            .agent-avatar {{
                width: 44px;
                height: 44px;
                border-radius: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 18px;
                font-weight: 600;
                color: #fff;
            }}
            
            .agent-info {{
                flex: 1;
            }}
            
            .agent-name {{
                font-size: 15px;
                font-weight: 600;
                color: #fff;
                margin-bottom: 4px;
            }}
            
            .agent-tags {{
                display: flex;
                gap: 6px;
                flex-wrap: wrap;
            }}
            
            .tag {{
                font-size: 11px;
                padding: 3px 8px;
                background: rgba(99, 102, 241, 0.15);
                color: #a5b4fc;
                border-radius: 6px;
                font-weight: 500;
            }}
            
            .agent-meta {{
                display: flex;
                flex-direction: column;
                align-items: flex-end;
                gap: 6px;
            }}
            
            .reputation {{
                font-size: 13px;
                color: #fbbf24;
                font-weight: 500;
            }}
            
            .online-dot {{
                width: 8px;
                height: 8px;
                background: #22c55e;
                border-radius: 50%;
                box-shadow: 0 0 8px #22c55e;
            }}
            
            /* Skills List */
            .skill-item {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 14px;
                background: rgba(255,255,255,0.02);
                border-radius: 12px;
                margin-bottom: 8px;
                transition: all 0.2s;
            }}
            
            .skill-item:hover {{
                background: rgba(255,255,255,0.05);
            }}
            
            .skill-icon {{
                font-size: 20px;
            }}
            
            .skill-name {{
                flex: 1;
                font-size: 14px;
                font-weight: 500;
                color: #e4e4e7;
            }}
            
            .skill-stats {{
                font-size: 13px;
                color: #71717a;
            }}
            
            /* Requests */
            .request-item {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 14px;
                background: rgba(251, 191, 36, 0.05);
                border: 1px solid rgba(251, 191, 36, 0.15);
                border-radius: 12px;
                margin-bottom: 8px;
            }}
            
            .request-icon {{
                font-size: 18px;
            }}
            
            .request-text {{
                flex: 1;
                font-size: 14px;
                color: #a1a1aa;
            }}
            
            .request-text strong {{
                color: #fbbf24;
            }}
            
            .request-by {{
                font-size: 12px;
                color: #52525b;
            }}
            
            /* Empty State */
            .empty-state {{
                text-align: center;
                padding: 40px 20px;
                color: #52525b;
            }}
            
            .empty-state-icon {{
                font-size: 48px;
                margin-bottom: 16px;
                opacity: 0.5;
            }}
            
            .empty-state-text {{
                font-size: 14px;
            }}
            
            /* API Section */
            .api-section {{
                background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.05) 100%);
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 24px;
                padding: 32px;
            }}
            
            .api-header {{
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
            }}
            
            .api-title {{
                font-size: 18px;
                font-weight: 600;
                color: #fff;
            }}
            
            .api-badge {{
                font-size: 12px;
                padding: 4px 10px;
                background: rgba(34, 197, 94, 0.2);
                color: #4ade80;
                border-radius: 20px;
                font-weight: 500;
            }}
            
            .endpoint {{
                font-family: 'SF Mono', Monaco, monospace;
                font-size: 14px;
                color: #a5b4fc;
                margin-bottom: 16px;
            }}
            
            .code-block {{
                background: rgba(0,0,0,0.3);
                border-radius: 12px;
                padding: 16px;
                margin-bottom: 10px;
                overflow-x: auto;
            }}
            
            .code-block code {{
                font-family: 'SF Mono', Monaco, monospace;
                font-size: 13px;
                color: #a5b4fc;
            }}
            
            /* Footer */
            .footer {{
                text-align: center;
                padding: 40px;
                color: #52525b;
                font-size: 14px;
            }}
            
            .footer a {{
                color: #6366f1;
                text-decoration: none;
            }}
            
            /* Responsive */
            @media (max-width: 1200px) {{
                .stats-grid {{ grid-template-columns: repeat(3, 1fr); }}
                .main-grid {{ grid-template-columns: 1fr; }}
            }}
            
            @media (max-width: 768px) {{
                .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
                .logo-text {{ font-size: 28px; }}
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
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon purple">↔️</div>
                        <span class="card-title">Live Activity</span>
                    </div>
                    {transfers_html if transfers_html else '''
                    <div class="empty-state">
                        <div class="empty-state-icon">🔄</div>
                        <div class="empty-state-text">No transfers yet.<br>Be the first to share a skill!</div>
                    </div>
                    '''}
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon blue">🤖</div>
                        <span class="card-title">Agents in Network</span>
                    </div>
                    {agents_html if agents_html else '''
                    <div class="empty-state">
                        <div class="empty-state-icon">🤖</div>
                        <div class="empty-state-text">No agents yet.<br>Register your agent to join!</div>
                    </div>
                    '''}
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon green">🛠️</div>
                        <span class="card-title">Popular Skills</span>
                    </div>
                    {skills_html if skills_html else '''
                    <div class="empty-state">
                        <div class="empty-state-icon">🛠️</div>
                        <div class="empty-state-text">No skills published yet.</div>
                    </div>
                    '''}
                    
                    <div class="card-header" style="margin-top: 24px;">
                        <div class="card-icon orange">🔍</div>
                        <span class="card-title">Skill Requests</span>
                    </div>
                    {requests_html if requests_html else '''
                    <div class="empty-state" style="padding: 20px;">
                        <div class="empty-state-text">No open requests</div>
                    </div>
                    '''}
                </div>
            </div>
            
            <div class="api-section">
                <div class="api-header">
                    <span class="api-title">🔌 API for Join39 Agents</span>
                    <span class="api-badge">Ready</span>
                </div>
                <div class="endpoint">POST /api/napster</div>
                <div class="code-block">
                    <code>{{"action": "register", "params": {{"agent_id": "...", "name": "...", "skills": ["..."]}}}}</code>
                </div>
                <div class="code-block">
                    <code>{{"action": "discover", "params": {{"skills_needed": ["weather", "translate"]}}}}</code>
                </div>
                <div class="code-block">
                    <code>{{"action": "share", "params": {{"from_agent_id": "...", "to_agent_id": "...", "skill_name": "..."}}}}</code>
                </div>
            </div>
            
            <footer class="footer">
                Built for the <a href="https://join39.org">Join39/NANDA Hackathon</a> at MIT 🚀
            </footer>
        </div>
        
        <script>
            // Auto-refresh every 10 seconds
            setTimeout(() => location.reload(), 10000);
        </script>
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
