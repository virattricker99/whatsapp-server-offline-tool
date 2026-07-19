"""
Virat King - Portfolio Website
Complete Single File Flask Application with Frontend + Backend + Database
Production Ready for Render Deployment
"""

import os
import sqlite3
import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify, session
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets

# Initialize Flask App
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'portfolio.db')

# Initialize Session
Session(app)

# Ensure instance folder exists
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance'), exist_ok=True)


# ==================== DATABASE SETUP ====================

def init_db():
    """Initialize database with all required tables"""
    db_path = app.config['DATABASE']
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create Contacts Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(120) NOT NULL,
            phone VARCHAR(20),
            subject VARCHAR(200),
            message TEXT NOT NULL,
            is_read BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            replied_at TIMESTAMP NULL
        )
    ''')
    
    # Create Admin Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            email VARCHAR(120),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create Site Visits Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS site_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address VARCHAR(50),
            user_agent TEXT,
            page_visited VARCHAR(200),
            visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn


def insert_sample_data():
    """Insert default admin if not exists"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM admin_users')
    admin_count = cursor.fetchone()[0]
    
    if admin_count == 0:
        default_password = generate_password_hash('admin123')
        cursor.execute('''
            INSERT INTO admin_users (username, password_hash, email)
            VALUES (?, ?, ?)
        ''', ('admin', default_password, 'admin@portfolio.com'))
        conn.commit()
        print("✅ Default admin created!")
    
    conn.close()


# ==================== HTML TEMPLATE ====================

INDEX_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Virat King - Professional Software Developer & Full Stack Web Developer Portfolio">
    <meta name="keywords" content="software developer, web developer, full stack, python, react, flask">
    <meta name="author" content="Virat King">
    <title>Virat King 👑 | Software Developer & Web Developer</title>
    
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://unpkg.com/aos@2.3.1/dist/aos.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    
    <style>
        :root {
            --primary: #0a0a0a;
            --secondary: #1a0a0a;
            --accent-1: #F4320B;
            --accent-2: #FF1493;
            --accent-3: #FF8C00;
            --accent-4: #FFD700;
            --accent-5: #9400D3;
            --accent-6: #00BFFF;
            --accent-7: #32CD32;
            --text-light: #FFFAFA;
            --text-muted: #D3D3D3;
            --glass-bg: rgba(255, 255, 255, 0.03);
            --glass-border: rgba(255, 255, 255, 0.1);
            --gradient-1: linear-gradient(135deg, #F4320B, #FF1493, #FF8C00, #FFD700);
            --gradient-2: linear-gradient(135deg, #9400D3, #00BFFF, #32CD32);
            --gradient-3: linear-gradient(135deg, #8B0000, #C71585, #FF4500);
            --gradient-4: linear-gradient(135deg, #4169E1, #8A2BE2, #FF1493);
            --gradient-5: linear-gradient(135deg, #2E8B57, #40E0D0, #87CEEB);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Poppins', sans-serif;
            background: var(--primary);
            color: var(--text-light);
            overflow-x: hidden;
        }

        .animated-gradient-bg {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1;
            background: linear-gradient(45deg, #0a0a0a 0%, #1a0505 25%, #0a0a15 50%, #150505 75%, #0a0a0a 100%);
            background-size: 400% 400%;
            animation: gradientShift 20s ease infinite;
        }

        @keyframes gradientShift {
            0% { background-position: 0% 50%; }
            25% { background-position: 100% 0%; }
            50% { background-position: 100% 100%; }
            75% { background-position: 0% 100%; }
            100% { background-position: 0% 50%; }
        }

        .color-orbs {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; overflow: hidden;
        }

        .orb {
            position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.15;
            animation: orbFloat 20s infinite ease-in-out;
        }

        .orb:nth-child(1) { width: 400px; height: 400px; background: #F4320B; top: -100px; left: -100px; animation-delay: 0s; }
        .orb:nth-child(2) { width: 350px; height: 350px; background: #FF1493; top: 60%; right: -100px; animation-delay: -5s; }
        .orb:nth-child(3) { width: 300px; height: 300px; background: #FF8C00; bottom: -100px; left: 30%; animation-delay: -10s; }
        .orb:nth-child(4) { width: 350px; height: 350px; background: #9400D3; top: 30%; left: 50%; animation-delay: -15s; }
        .orb:nth-child(5) { width: 250px; height: 250px; background: #00BFFF; top: -50px; right: 30%; animation-delay: -8s; }
        .orb:nth-child(6) { width: 300px; height: 300px; background: #32CD32; bottom: 20%; right: 20%; animation-delay: -12s; }
        .orb:nth-child(7) { width: 200px; height: 200px; background: #FFD700; top: 50%; left: 10%; animation-delay: -3s; }

        @keyframes orbFloat {
            0%, 100% { transform: translate(0, 0) scale(1); }
            25% { transform: translate(100px, -50px) scale(1.2); }
            50% { transform: translate(-50px, 100px) scale(0.8); }
            75% { transform: translate(-100px, -100px) scale(1.1); }
        }

        #loading-screen {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: var(--primary); display: flex; align-items: center; justify-content: center;
            z-index: 10000; transition: opacity 0.5s ease;
        }

        .loader { text-align: center; }
        .loader-orbits { position: relative; width: 100px; height: 100px; margin: 0 auto 30px; }
        .loader-orbit { position: absolute; border-radius: 50%; border: 2px solid transparent; animation: orbitSpin 2s linear infinite; }
        .loader-orbit:nth-child(1) { width: 100%; height: 100%; border-top-color: #F4320B; border-right-color: #FF1493; animation-duration: 1.5s; }
        .loader-orbit:nth-child(2) { width: 70%; height: 70%; top: 15%; left: 15%; border-bottom-color: #FF8C00; border-left-color: #FFD700; animation-duration: 2s; animation-direction: reverse; }
        .loader-orbit:nth-child(3) { width: 40%; height: 40%; top: 30%; left: 30%; border-top-color: #9400D3; border-right-color: #00BFFF; animation-duration: 1.8s; }

        @keyframes orbitSpin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .loader h2 { background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; font-size: 1.5rem; }

        .scroll-progress { position: fixed; top: 0; left: 0; height: 3px; background: var(--gradient-1); z-index: 9999; transition: width 0.1s ease; }

        .navbar { background: rgba(10, 10, 10, 0.9); backdrop-filter: blur(20px); padding: 15px 0; transition: all 0.3s ease; border-bottom: 1px solid rgba(244, 50, 11, 0.2); }
        .navbar.scrolled { padding: 10px 0; box-shadow: 0 5px 30px rgba(244, 50, 11, 0.3); border-bottom: 1px solid rgba(255, 20, 147, 0.3); }

        .brand-text { font-size: 28px; font-weight: 700; background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; text-decoration: none; }
        .brand-dot { -webkit-text-fill-color: #FFD700; }

        .nav-link { color: var(--text-light) !important; margin: 0 10px; font-weight: 500; position: relative; transition: all 0.3s ease; }
        .nav-link::after { content: ''; position: absolute; bottom: -5px; left: 0; width: 0; height: 2px; background: var(--gradient-1); transition: width 0.3s ease; }
        .nav-link:hover::after { width: 100%; }

        .btn-theme-toggle { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.2); color: var(--text-light); border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; padding: 0; transition: all 0.3s ease; }
        .btn-theme-toggle:hover { background: var(--gradient-1); border-color: transparent; color: white; }

        .hero-section { position: relative; min-height: 100vh; display: flex; align-items: center; overflow: hidden; }
        .welcome-text { color: #A9A9A9; font-size: 1.1rem; font-weight: 500; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 10px; }
        .welcome-text .highlight { background: var(--gradient-3); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; font-weight: 700; }
        .hero-title { font-size: 3.5rem; font-weight: 700; margin-bottom: 20px; color: var(--text-light); }
        .gradient-text { background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
        .typing-container { font-size: 2rem; font-weight: 600; margin-bottom: 20px; min-height: 50px; background: var(--gradient-4); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
        .cursor { animation: blink 0.7s infinite; -webkit-text-fill-color: #FFD700; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        .hero-description { font-size: 1.1rem; color: var(--text-muted); margin-bottom: 30px; line-height: 1.8; }
        .hero-buttons { display: flex; flex-wrap: wrap; gap: 15px; }
        .hero-buttons .btn { padding: 12px 30px; border-radius: 50px; font-weight: 500; transition: all 0.3s ease; }

        .btn-gradient { background: var(--gradient-1); color: white; border: none; position: relative; overflow: hidden; z-index: 1; }
        .btn-gradient::before { content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%; background: var(--gradient-3); transition: left 0.5s ease; z-index: -1; }
        .btn-gradient:hover::before { left: 0; }
        .btn-gradient:hover { transform: translateY(-3px); box-shadow: 0 10px 40px rgba(244, 50, 11, 0.5); color: white; }

        .btn-outline-light { border: 2px solid rgba(255, 255, 255, 0.3); color: var(--text-light); background: transparent; }
        .btn-outline-light:hover { background: rgba(255, 255, 255, 0.1); color: white; border-color: #FFD700; box-shadow: 0 10px 30px rgba(255, 215, 0, 0.3); }

        .hero-image-container { position: relative; display: flex; justify-content: center; }
        .image-wrapper { width: 350px; height: 350px; border-radius: 50%; padding: 5px; background: var(--gradient-1); animation: float 3s ease-in-out infinite, rotateGlow 6s linear infinite; overflow: hidden; box-shadow: 0 0 30px rgba(244, 50, 11, 0.4), 0 0 60px rgba(255, 20, 147, 0.3), 0 0 90px rgba(255, 140, 0, 0.2); }
        @keyframes rotateGlow { 0% { box-shadow: 0 0 30px rgba(244, 50, 11, 0.4), 0 0 60px rgba(255, 20, 147, 0.3), 0 0 90px rgba(255, 140, 0, 0.2); } 33% { box-shadow: 0 0 30px rgba(255, 20, 147, 0.4), 0 0 60px rgba(148, 0, 211, 0.3), 0 0 90px rgba(0, 191, 255, 0.2); } 66% { box-shadow: 0 0 30px rgba(255, 215, 0, 0.4), 0 0 60px rgba(255, 140, 0, 0.3), 0 0 90px rgba(50, 205, 50, 0.2); } 100% { box-shadow: 0 0 30px rgba(244, 50, 11, 0.4), 0 0 60px rgba(255, 20, 147, 0.3), 0 0 90px rgba(255, 140, 0, 0.2); } }
        .hero-image { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; border: 5px solid var(--primary); }
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-20px); } }

        .social-icons { display: flex; gap: 15px; }
        .social-icon { width: 45px; height: 45px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: var(--text-light); font-size: 1.2rem; transition: all 0.3s ease; text-decoration: none; position: relative; overflow: hidden; }
        .social-icon::before { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: var(--gradient-1); opacity: 0; transition: opacity 0.3s ease; border-radius: 50%; }
        .social-icon:hover::before { opacity: 1; }
        .social-icon i { position: relative; z-index: 1; }
        .social-icon:hover { transform: translateY(-5px); color: white; border-color: transparent; box-shadow: 0 10px 30px rgba(244, 50, 11, 0.4); }

        .glass-card { background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; padding: 30px; backdrop-filter: blur(10px); transition: all 0.5s ease; position: relative; overflow: hidden; }
        .glass-card::before { content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.05), transparent); transition: left 0.5s ease; }
        .glass-card:hover::before { left: 100%; }
        .glass-card:hover { transform: translateY(-10px); box-shadow: 0 20px 60px rgba(244, 50, 11, 0.2), 0 0 0 1px rgba(255, 215, 0, 0.2); border-color: rgba(255, 215, 0, 0.3); }

        section { padding: 100px 0; position: relative; }
        .section-header { text-align: center; margin-bottom: 60px; }
        .section-header h2 { font-size: 2.5rem; font-weight: 700; color: var(--text-light); margin-bottom: 10px; }
        .section-subtitle { color: var(--text-muted); font-size: 1.1rem; }

        .about-image-wrapper { border-radius: 20px; overflow: hidden; border: 3px solid rgba(244, 50, 11, 0.3); box-shadow: 0 0 40px rgba(244, 50, 11, 0.2); transition: all 0.5s ease; }
        .about-image-wrapper:hover { box-shadow: 0 0 60px rgba(255, 20, 147, 0.4); border-color: rgba(255, 20, 147, 0.5); }
        .about-image-wrapper img { width: 100%; height: auto; object-fit: cover; }
        .about-content h3 { background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 20px; }
        .about-content p { color: var(--text-muted); line-height: 1.8; }

        .about-info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-top: 30px; }
        .info-card { text-align: center; padding: 20px; transition: all 0.5s ease; }
        .info-card:nth-child(1):hover { box-shadow: 0 0 30px rgba(244, 50, 11, 0.3); }
        .info-card:nth-child(2):hover { box-shadow: 0 0 30px rgba(255, 20, 147, 0.3); }
        .info-card:nth-child(3):hover { box-shadow: 0 0 30px rgba(255, 140, 0, 0.3); }
        .info-card:nth-child(4):hover { box-shadow: 0 0 30px rgba(148, 0, 211, 0.3); }
        .info-card i { font-size: 2rem; margin-bottom: 10px; background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
        .info-card h4 { color: var(--text-light); font-size: 1rem; margin-bottom: 5px; }
        .info-card p { color: var(--text-muted); font-size: 0.9rem; }

        .professional-objective { padding: 25px; background: rgba(255, 255, 255, 0.03); border-radius: 15px; border-left: 4px solid; border-image: var(--gradient-1) 1; }
        .professional-objective h4 { background: var(--gradient-3); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 15px; }

        .skill-category { margin-bottom: 40px; }
        .category-title { color: var(--text-light); margin-bottom: 20px; font-size: 1.5rem; }
        .category-title i { margin-right: 10px; background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
        .skills-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .skill-card { text-align: center; padding: 25px; transition: all 0.5s ease; }
        .skill-card i { font-size: 3rem; margin-bottom: 15px; transition: all 0.3s ease; }
        .skill-card:hover i { transform: scale(1.2); }
        .skill-card h4 { font-size: 1.1rem; margin-bottom: 15px; color: var(--text-light); }
        .progress { height: 8px; background: rgba(255, 255, 255, 0.1); border-radius: 10px; overflow: hidden; }
        .progress-bar { border-radius: 10px; font-size: 0.7rem; line-height: 8px; color: white; text-align: right; padding-right: 5px; animation: progressGlow 2s ease infinite; }
        @keyframes progressGlow { 0%, 100% { box-shadow: 0 0 5px rgba(244, 50, 11, 0.5); } 50% { box-shadow: 0 0 20px rgba(255, 215, 0, 0.8); } }

        .services-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 25px; }
        .service-card { text-align: center; padding: 40px 30px; }
        .service-card i { font-size: 3rem; margin-bottom: 20px; background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; transition: all 0.3s ease; }
        .service-card:hover i { transform: scale(1.3) rotate(360deg); }
        .service-card h3 { font-size: 1.3rem; margin-bottom: 15px; color: var(--text-light); }
        .service-card p { color: var(--text-muted); line-height: 1.6; }

        .project-card { padding: 0; overflow: hidden; position: relative; }
        .project-badge { position: absolute; top: 20px; right: 20px; background: var(--gradient-1); color: white; padding: 8px 20px; border-radius: 50px; font-size: 0.9rem; z-index: 1; animation: badgeGlow 2s ease infinite; }
        @keyframes badgeGlow { 0%, 100% { box-shadow: 0 0 10px rgba(244, 50, 11, 0.5); } 50% { box-shadow: 0 0 30px rgba(255, 215, 0, 0.8); } }
        .project-image img { width: 100%; height: 100%; object-fit: cover; border-radius: 20px 0 0 20px; }
        .tech-stack { margin: 20px 0; }
        .tech-badge { display: inline-block; background: rgba(244, 50, 11, 0.1); color: #FF8C00; padding: 5px 15px; border-radius: 50px; margin: 5px; font-size: 0.85rem; border: 1px solid rgba(255, 140, 0, 0.3); transition: all 0.3s ease; }
        .tech-badge:hover { background: rgba(244, 50, 11, 0.2); transform: translateY(-3px); }
        .project-features { margin: 20px 0; }
        .project-features h5 { color: var(--text-light); margin-bottom: 15px; }
        .project-features ul { list-style: none; padding: 0; }
        .project-features li { color: var(--text-muted); margin-bottom: 10px; display: flex; align-items: center; }
        .project-features li i { color: #32CD32; margin-right: 10px; }
        .project-buttons { display: flex; gap: 15px; margin-top: 20px; }

        .timeline { position: relative; padding: 40px 0; }
        .timeline::before { content: ''; position: absolute; left: 50%; top: 0; bottom: 0; width: 3px; background: var(--gradient-1); transform: translateX(-50%); animation: timelineGlow 3s ease infinite; }
        @keyframes timelineGlow { 0%, 100% { box-shadow: 0 0 10px rgba(244, 50, 11, 0.5); } 50% { box-shadow: 0 0 30px rgba(255, 215, 0, 0.8); } }
        .timeline-item { margin-bottom: 50px; position: relative; width: 50%; }
        .timeline-item:nth-child(odd) { left: 0; padding-right: 50px; }
        .timeline-item:nth-child(even) { left: 50%; padding-left: 50px; }
        .timeline-content { padding: 25px; }
        .timeline-date { display: inline-block; background: var(--gradient-1); color: white; padding: 5px 20px; border-radius: 50px; font-size: 0.9rem; margin-bottom: 15px; }
        .timeline-content h3 { color: var(--text-light); margin-bottom: 10px; }

        .info-item { display: flex; align-items: center; margin-bottom: 25px; padding: 20px; background: rgba(255, 255, 255, 0.03); border-radius: 15px; border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.3s ease; }
        .info-item:hover { border-color: rgba(244, 50, 11, 0.5); box-shadow: 0 10px 30px rgba(244, 50, 11, 0.2); }
        .info-item i { width: 50px; height: 50px; background: var(--gradient-1); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 20px; font-size: 1.2rem; color: white; }
        .info-item h5 { color: var(--text-light); margin-bottom: 5px; }
        .info-item p, .info-item a { color: var(--text-muted); margin: 0; text-decoration: none; }

        .contact-form .form-control { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); color: var(--text-light); padding: 12px 20px; border-radius: 10px; transition: all 0.3s ease; }
        .contact-form .form-control:focus { background: rgba(255, 255, 255, 0.1); border-color: #FF8C00; box-shadow: 0 0 0 3px rgba(255, 140, 0, 0.2); color: white; }
        .contact-form .form-control::placeholder { color: var(--text-muted); }
        .contact-form textarea { resize: vertical; min-height: 120px; }

        .alert { border-radius: 10px; padding: 15px 20px; margin-bottom: 20px; }
        .alert-success { background: rgba(50, 205, 50, 0.2); border: 1px solid rgba(50, 205, 50, 0.3); color: #32CD32; }
        .alert-error { background: rgba(244, 50, 11, 0.2); border: 1px solid rgba(244, 50, 11, 0.3); color: #F4320B; }

        .footer { background: linear-gradient(135deg, #0a0a0a, #1a0505, #0a0a15); padding: 50px 0 30px; text-align: center; border-top: 1px solid rgba(244, 50, 11, 0.3); position: relative; overflow: hidden; }
        .footer::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--gradient-1); animation: footerGlow 3s ease infinite; }
        @keyframes footerGlow { 0%, 100% { box-shadow: 0 0 10px rgba(244, 50, 11, 0.5); } 50% { box-shadow: 0 0 30px rgba(255, 215, 0, 0.8); } }
        .footer h3 { background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; font-size: 1.5rem; margin-bottom: 10px; display: inline-block; }
        .crown { -webkit-text-fill-color: #FFD700; }
        .footer .subtitle { background: var(--gradient-3); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; font-size: 1rem; margin-bottom: 10px; font-weight: 500; }
        .footer p { color: var(--text-muted); margin-bottom: 20px; }
        .footer-social { margin: 20px 0; display: flex; justify-content: center; gap: 15px; }
        .footer-social a { display: inline-flex; width: 45px; height: 45px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 50%; align-items: center; justify-content: center; color: var(--text-light); transition: all 0.3s ease; text-decoration: none; }
        .footer-social a:hover { background: var(--gradient-1); transform: translateY(-5px); box-shadow: 0 10px 30px rgba(244, 50, 11, 0.4); border-color: transparent; }
        .copyright { color: var(--text-muted); margin-top: 20px; font-size: 0.9rem; letter-spacing: 1px; }
        .powered-by { margin-top: 15px; font-size: 0.85rem; background: var(--gradient-1); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; font-weight: 500; }
        .heart { color: #FF1493; animation: heartbeat 1.5s infinite; display: inline-block; -webkit-text-fill-color: #FF1493; }
        @keyframes heartbeat { 0%, 100% { transform: scale(1); } 10%, 30% { transform: scale(1.3); } 20%, 40% { transform: scale(1); } }

        .scroll-top-btn { position: fixed; bottom: 30px; right: 30px; width: 50px; height: 50px; background: var(--gradient-1); border: none; border-radius: 50%; color: white; display: none; align-items: center; justify-content: center; z-index: 999; cursor: pointer; font-size: 1.2rem; animation: pulse 2s infinite; box-shadow: 0 5px 30px rgba(244, 50, 11, 0.5); }
        @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(244, 50, 11, 0.6); } 70% { box-shadow: 0 0 0 20px rgba(244, 50, 11, 0); } 100% { box-shadow: 0 0 0 0 rgba(244, 50, 11, 0); } }

        .whatsapp-float { position: fixed; bottom: 100px; right: 30px; width: 60px; height: 60px; background: #25D366; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 2rem; z-index: 999; text-decoration: none; animation: whatsappPulse 2s infinite; box-shadow: 0 5px 30px rgba(37, 211, 102, 0.5); }
        @keyframes whatsappPulse { 0% { box-shadow: 0 0 0 0 rgba(37, 211, 102, 0.6); } 70% { box-shadow: 0 0 0 20px rgba(37, 211, 102, 0); } 100% { box-shadow: 0 0 0 0 rgba(37, 211, 102, 0); } }
        .whatsapp-float:hover { color: white; transform: scale(1.1); }

        @media (max-width: 992px) { .hero-title { font-size: 2.5rem; } .typing-container { font-size: 1.3rem; } .image-wrapper { width: 280px; height: 280px; margin-top: 30px; } .project-image img { border-radius: 20px 20px 0 0; } }
        @media (max-width: 768px) { .hero-title { font-size: 2rem; } .typing-container { font-size: 1.1rem; } .image-wrapper { width: 250px; height: 250px; margin-top: 50px; } .timeline::before { left: 30px; } .timeline-item { width: 100%; padding-left: 80px; padding-right: 0; } .timeline-item:nth-child(even) { left: 0; } .section-header h2 { font-size: 2rem; } .about-info-grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="animated-gradient-bg"></div>
    <div class="color-orbs">
        <div class="orb"></div><div class="orb"></div><div class="orb"></div><div class="orb"></div>
        <div class="orb"></div><div class="orb"></div><div class="orb"></div>
    </div>

    <div id="loading-screen">
        <div class="loader">
            <div class="loader-orbits">
                <div class="loader-orbit"></div><div class="loader-orbit"></div><div class="loader-orbit"></div>
            </div>
            <h2>Virat King 👑</h2>
        </div>
    </div>

    <div class="scroll-progress"></div>

    <nav class="navbar navbar-expand-lg fixed-top">
        <div class="container">
            <a class="navbar-brand" href="#"><span class="brand-text">Virat King<span class="brand-dot">.</span></span></a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item"><a class="nav-link" href="#home">Home</a></li>
                    <li class="nav-item"><a class="nav-link" href="#about">About</a></li>
                    <li class="nav-item"><a class="nav-link" href="#skills">Skills</a></li>
                    <li class="nav-item"><a class="nav-link" href="#services">Services</a></li>
                    <li class="nav-item"><a class="nav-link" href="#projects">Projects</a></li>
                    <li class="nav-item"><a class="nav-link" href="#education">Education</a></li>
                    <li class="nav-item"><a class="nav-link" href="#contact">Contact</a></li>
                </ul>
                <button class="btn btn-theme-toggle ms-3" id="themeToggle"><i class="fas fa-moon"></i></button>
            </div>
        </div>
    </nav>

    <section id="home" class="hero-section">
        <div class="container">
            <div class="row align-items-center min-vh-100">
                <div class="col-lg-7" data-aos="fade-right" data-aos-duration="1000">
                    <p class="welcome-text"><span class="highlight">I AM VIRAT</span></p>
                    <h1 class="hero-title">Hi, I'm <span class="gradient-text">Virat King 👑</span></h1>
                    <div class="typing-container"><span id="typing-text"></span><span class="cursor">|</span></div>
                    <p class="hero-description">A passionate Software Developer and Web Developer who enjoys transforming innovative ideas into modern, responsive, and high-performance digital solutions.</p>
                    <div class="hero-buttons">
                        <a href="#contact" class="btn btn-gradient">Hire Me <i class="fas fa-arrow-right ms-2"></i></a>
                        <a href="#" class="btn btn-outline-light">Download Resume <i class="fas fa-download ms-2"></i></a>
                        <a href="#contact" class="btn btn-outline-light">Contact Me <i class="fas fa-envelope ms-2"></i></a>
                    </div>
                    <div class="social-icons mt-4">
                        <a href="#" class="social-icon"><i class="fab fa-linkedin"></i></a>
                        <a href="#" class="social-icon"><i class="fab fa-github"></i></a>
                        <a href="#" class="social-icon"><i class="fab fa-instagram"></i></a>
                        <a href="#" class="social-icon"><i class="fab fa-snapchat"></i></a>
                        <a href="mailto:vs0371926@gmail.com" class="social-icon"><i class="fas fa-envelope"></i></a>
                    </div>
                </div>
                <div class="col-lg-5 text-center" data-aos="fade-left" data-aos-duration="1000">
                    <div class="hero-image-container">
                        <div class="image-wrapper">
                            <img src="https://i.ibb.co/xqw8J9PY/Screenshot-2026-07-13-18-15-26-72-92460851df6f172a4592fca41cc2d2e6.jpg" alt="Virat King" class="hero-image">
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section id="about" class="about-section">
        <div class="container">
            <div class="section-header" data-aos="fade-up"><h2>About <span class="gradient-text">Me</span></h2><p class="section-subtitle">Get to know me better</p></div>
            <div class="row align-items-center">
                <div class="col-lg-5 mb-4 mb-lg-0" data-aos="fade-right">
                    <div class="about-image-wrapper"><img src="https://i.ibb.co/xqw8J9PY/Screenshot-2026-07-13-18-15-26-72-92460851df6f172a4592fca41cc2d2e6.jpg" alt="About Virat King"></div>
                </div>
                <div class="col-lg-7" data-aos="fade-left">
                    <div class="about-content">
                        <h3>Professional Summary</h3>
                        <p>Motivated and results-driven Software Developer and Web Developer with a strong foundation in software engineering, modern web technologies, and problem-solving. Passionate about designing secure, scalable, and user-friendly applications that deliver real-world impact. Proficient in HTML5, CSS3, JavaScript, Bootstrap 5, React.js, Node.js, Python (Flask), SQLite, MySQL, Git, and GitHub.</p>
                        <div class="about-info-grid">
                            <div class="info-card glass-card"><i class="fas fa-user-graduate"></i><h4>Qualification</h4><p>BCA + MCA</p></div>
                            <div class="info-card glass-card"><i class="fas fa-briefcase"></i><h4>Experience</h4><p>Freelance Developer</p></div>
                            <div class="info-card glass-card"><i class="fas fa-code"></i><h4>Specialization</h4><p>Full Stack Development</p></div>
                            <div class="info-card glass-card"><i class="fas fa-shield-alt"></i><h4>Focus</h4><p>Cybersecurity & AI</p></div>
                        </div>
                        <div class="professional-objective mt-4">
                            <h4><i class="fas fa-bullseye"></i> Professional Objective</h4>
                            <p>"I believe technology should solve real-world problems through innovation, creativity, and clean engineering. My goal is to build secure, scalable, and user-friendly digital solutions that create meaningful impact."</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section id="skills" class="skills-section">
        <div class="container">
            <div class="section-header" data-aos="fade-up"><h2>My <span class="gradient-text">Skills</span></h2><p class="section-subtitle">Technologies I work with</p></div>
            <div class="skill-category" data-aos="fade-up">
                <h3 class="category-title"><i class="fas fa-laptop-code"></i> Frontend</h3>
                <div class="skills-grid">
                    <div class="skill-card glass-card"><i class="fab fa-html5" style="color: #E44D26;"></i><h4>HTML5</h4><div class="progress"><div class="progress-bar" style="width: 95%; background: linear-gradient(135deg, #E44D26, #F4320B);">95%</div></div></div>
                    <div class="skill-card glass-card"><i class="fab fa-css3-alt" style="color: #1572B6;"></i><h4>CSS3</h4><div class="progress"><div class="progress-bar" style="width: 90%; background: linear-gradient(135deg, #1572B6, #00BFFF);">90%</div></div></div>
                    <div class="skill-card glass-card"><i class="fab fa-js" style="color: #F7DF1E;"></i><h4>JavaScript</h4><div class="progress"><div class="progress-bar" style="width: 85%; background: linear-gradient(135deg, #F7DF1E, #FFD700);">85%</div></div></div>
                    <div class="skill-card glass-card"><i class="fab fa-bootstrap" style="color: #7952B3;"></i><h4>Bootstrap</h4><div class="progress"><div class="progress-bar" style="width: 90%; background: linear-gradient(135deg, #7952B3, #9400D3);">90%</div></div></div>
                </div>
            </div>
            <div class="skill-category" data-aos="fade-up">
                <h3 class="category-title"><i class="fas fa-server"></i> Backend</h3>
                <div class="skills-grid">
                    <div class="skill-card glass-card"><i class="fab fa-python" style="color: #3776AB;"></i><h4>Python</h4><div class="progress"><div class="progress-bar" style="width: 88%; background: linear-gradient(135deg, #3776AB, #4169E1);">88%</div></div></div>
                    <div class="skill-card glass-card"><i class="fas fa-flask"></i><h4>Flask</h4><div class="progress"><div class="progress-bar" style="width: 85%; background: linear-gradient(135deg, #666, #2F4F4F);">85%</div></div></div>
                </div>
            </div>
        </div>
    </section>

    <section id="services" class="services-section">
        <div class="container">
            <div class="section-header" data-aos="fade-up"><h2>My <span class="gradient-text">Services</span></h2><p class="section-subtitle">What I offer</p></div>
            <div class="services-grid">
                <div class="service-card glass-card" data-aos="zoom-in"><i class="fas fa-globe"></i><h3>Website Development</h3><p>Custom responsive websites built with modern technologies.</p></div>
                <div class="service-card glass-card" data-aos="zoom-in" data-aos-delay="100"><i class="fas fa-layer-group"></i><h3>Web Applications</h3><p>Scalable web apps with robust backend.</p></div>
                <div class="service-card glass-card" data-aos="zoom-in" data-aos-delay="200"><i class="fab fa-python"></i><h3>Python Development</h3><p>Custom Python solutions & automation.</p></div>
                <div class="service-card glass-card" data-aos="zoom-in" data-aos-delay="300"><i class="fas fa-file-code"></i><h3>Portfolio Websites</h3><p>Professional portfolio websites.</p></div>
            </div>
        </div>
    </section>

    <section id="projects" class="projects-section">
        <div class="container">
            <div class="section-header" data-aos="fade-up"><h2>Featured <span class="gradient-text">Projects</span></h2><p class="section-subtitle">My recent work</p></div>
            <div class="featured-project" data-aos="fade-up">
                <div class="project-card glass-card">
                    <div class="project-badge">Academic Project</div>
                    <div class="row">
                        <div class="col-lg-6 mb-4 mb-lg-0"><div class="project-image"><img src="https://via.placeholder.com/600x400/1a1a1a/FF8C00?text=AI+Phishing+Detection" alt="AI Phishing Detection"></div></div>
                        <div class="col-lg-6 p-4">
                            <h3>AI-Based Phishing Detection Tool</h3>
                            <p>Developed an intelligent AI-Based Phishing Detection Tool that identifies malicious websites, suspicious URLs, and phishing attacks.</p>
                            <div class="tech-stack">
                                <span class="tech-badge">HTML5</span><span class="tech-badge">CSS3</span><span class="tech-badge">JavaScript</span>
                                <span class="tech-badge">Bootstrap 5</span><span class="tech-badge">Python Flask</span><span class="tech-badge">ML</span>
                            </div>
                            <div class="project-features">
                                <h5>Key Features:</h5>
                                <ul>
                                    <li><i class="fas fa-check-circle"></i> Real-time phishing URL detection</li>
                                    <li><i class="fas fa-check-circle"></i> AI-powered URL risk analysis</li>
                                    <li><i class="fas fa-check-circle"></i> Risk score generation</li>
                                </ul>
                            </div>
                            <div class="project-buttons"><a href="#" class="btn btn-gradient">Live Demo</a><a href="#" class="btn btn-outline-light">GitHub</a></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section id="education" class="education-section">
        <div class="container">
            <div class="section-header" data-aos="fade-up"><h2>My <span class="gradient-text">Education</span></h2><p class="section-subtitle">Academic background</p></div>
            <div class="timeline">
                <div class="timeline-item" data-aos="fade-right"><div class="timeline-content glass-card"><div class="timeline-date">2018 - 2019</div><h3>12th (Science)</h3><p>Completed Higher Secondary Education with Science background.</p></div></div>
                <div class="timeline-item" data-aos="fade-left"><div class="timeline-content glass-card"><div class="timeline-date">2019 - 2022</div><h3>Bachelor of Computer Applications (BCA)</h3><p>Focused on programming, web development, database management & software engineering.</p></div></div>
                <div class="timeline-item" data-aos="fade-right"><div class="timeline-content glass-card"><div class="timeline-date">2022 - 2024</div><h3>Master of Computer Applications (MCA)</h3><p>Advanced knowledge in full-stack development, cloud computing, cybersecurity & AI.</p></div></div>
            </div>
        </div>
    </section>

    <section id="contact" class="contact-section">
        <div class="container">
            <div class="section-header" data-aos="fade-up"><h2>Get In <span class="gradient-text">Touch</span></h2><p class="section-subtitle">Let's work together</p></div>
            <div class="row">
                <div class="col-lg-5 mb-4 mb-lg-0" data-aos="fade-right">
                    <div class="contact-info">
                        <h3 class="mb-4">Contact Information</h3>
                        <div class="info-item"><i class="fas fa-phone"></i><div><h5>Phone</h5><p><a href="tel:+917310927827">+91 7310927827</a></p></div></div>
                        <div class="info-item"><i class="fas fa-envelope"></i><div><h5>Email</h5><p><a href="mailto:vs0371926@gmail.com">vs0371926@gmail.com</a></p><p><a href="mailto:viratking1978@gmail.com">viratking1978@gmail.com</a></p></div></div>
                        <div class="info-item"><i class="fab fa-whatsapp"></i><div><h5>WhatsApp</h5><p><a href="https://wa.me/917310927827" target="_blank">Chat on WhatsApp</a></p></div></div>
                    </div>
                </div>
                <div class="col-lg-7" data-aos="fade-left">
                    {% with messages = get_flashed_messages(with_categories=true) %}
                        {% if messages %}
                            {% for category, message in messages %}
                                <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                                    {{ message }}
                                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                                </div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}
                    <form class="contact-form glass-card" action="{{ url_for('submit_contact') }}" method="POST">
                        <h3 class="mb-4">Send Message</h3>
                        <div class="row">
                            <div class="col-md-6 mb-3"><input type="text" class="form-control" name="name" placeholder="Your Name" required></div>
                            <div class="col-md-6 mb-3"><input type="email" class="form-control" name="email" placeholder="Your Email" required></div>
                        </div>
                        <div class="mb-3"><input type="tel" class="form-control" name="phone" placeholder="Phone Number"></div>
                        <div class="mb-3"><input type="text" class="form-control" name="subject" placeholder="Subject"></div>
                        <div class="mb-3"><textarea class="form-control" name="message" rows="5" placeholder="Your Message" required></textarea></div>
                        <button type="submit" class="btn btn-gradient w-100">Send Message <i class="fas fa-paper-plane ms-2"></i></button>
                    </form>
                </div>
            </div>
        </div>
    </section>

    <footer class="footer">
        <div class="container">
            <div class="footer-content">
                <h3>Made by <span class="crown">Virat King 👑</span></h3>
                <p class="subtitle">Software Developer & Web Developer</p>
                <div class="footer-social">
                    <a href="#"><i class="fab fa-linkedin"></i></a>
                    <a href="#"><i class="fab fa-github"></i></a>
                    <a href="#"><i class="fab fa-instagram"></i></a>
                    <a href="#"><i class="fab fa-snapchat"></i></a>
                    <a href="mailto:vs0371926@gmail.com"><i class="fas fa-envelope"></i></a>
                </div>
                <p class="copyright">© 2026 Virat King 👑 | All Rights Reserved.</p>
                <p class="powered-by">Powered by <span style="-webkit-text-fill-color: #FF8C00;">Virat</span> | Built with <span class="heart">❤️</span> & Passion</p>
            </div>
        </div>
    </footer>

    <button class="scroll-top-btn" id="scrollTopBtn"><i class="fas fa-arrow-up"></i></button>
    <a href="https://wa.me/917310927827?text=Hi%20Virat%20King%20👑,%0A%0AI%20visited%20your%20portfolio%20website%20and%20I%20want%20to%20discuss%20a%20project%20with%20you.%0A%0AName:%0ACompany:%0AProject%20Details:%0A%0ALooking%20forward%20to%20working%20with%20you!" class="whatsapp-float" target="_blank"><i class="fab fa-whatsapp"></i></a>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://unpkg.com/aos@2.3.1/dist/aos.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        $(window).on('load', function() { setTimeout(function() { $('#loading-screen').fadeOut(500); }, 2000); });
        AOS.init({ duration: 1000, once: true, offset: 100 });

        $(window).scroll(function() {
            var scroll = $(window).scrollTop();
            var height = $(document).height() - $(window).height();
            var progress = (scroll / height) * 100;
            $('.scroll-progress').css('width', progress + '%');
            if ($(window).scrollTop() > 50) { $('.navbar').addClass('scrolled'); }
            else { $('.navbar').removeClass('scrolled'); }
        });

        $('a[href^="#"]').on('click', function(e) {
            e.preventDefault();
            var target = $(this.hash);
            if (target.length) { $('html, body').animate({ scrollTop: target.offset().top - 80 }, 800); }
        });

        const typingTexts = ['Software Developer', 'Full Stack Developer', 'Python Developer', 'Web Developer', 'Freelancer'];
        let textIndex = 0, charIndex = 0, isDeleting = false, typingSpeed = 100;
        function typeEffect() {
            const currentText = typingTexts[textIndex];
            if (isDeleting) { $('#typing-text').text(currentText.substring(0, charIndex - 1)); charIndex--; typingSpeed = 50; }
            else { $('#typing-text').text(currentText.substring(0, charIndex + 1)); charIndex++; typingSpeed = 100; }
            if (!isDeleting && charIndex === currentText.length) { typingSpeed = 2000; isDeleting = true; }
            else if (isDeleting && charIndex === 0) { isDeleting = false; textIndex = (textIndex + 1) % typingTexts.length; typingSpeed = 500; }
            setTimeout(typeEffect, typingSpeed);
        }
        typeEffect();

        $('#themeToggle').on('click', function() {
            $('body').toggleClass('light-mode');
            var icon = $(this).find('i');
            if ($('body').hasClass('light-mode')) { icon.removeClass('fa-moon').addClass('fa-sun'); localStorage.setItem('theme', 'light'); }
            else { icon.removeClass('fa-sun').addClass('fa-moon'); localStorage.setItem('theme', 'dark'); }
        });

        $(window).scroll(function() { if ($(window).scrollTop() > 500) $('#scrollTopBtn').fadeIn(); else $('#scrollTopBtn').fadeOut(); });
        $('#scrollTopBtn').on('click', function() { $('html, body').animate({ scrollTop: 0 }, 800); });

        // Track visit
        $.ajax({ url: '/track-visit', type: 'POST', contentType: 'application/json', data: JSON.stringify({ page: 'home' }) });

        console.log('🚀 Virat King 👑 | Software Developer | Full Color Spectrum Portfolio!');
    </script>
</body>
</html>
'''

ADMIN_LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - Virat King Portfolio</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: #0a0a0a; min-height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Poppins', sans-serif; }
        .login-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; padding: 40px; backdrop-filter: blur(10px); width: 100%; max-width: 400px; box-shadow: 0 20px 60px rgba(244,50,11,0.2); }
        h2 { background: linear-gradient(135deg, #F4320B, #FF1493, #FF8C00, #FFD700); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; margin-bottom: 30px; }
        .form-control { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 12px; border-radius: 10px; }
        .form-control:focus { background: rgba(255,255,255,0.1); border-color: #FF8C00; box-shadow: 0 0 0 3px rgba(255,140,0,0.2); color: white; }
        .btn-login { background: linear-gradient(135deg, #F4320B, #FF1493, #FF8C00); color: white; border: none; padding: 12px; border-radius: 10px; width: 100%; font-weight: 600; }
        .btn-login:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(244,50,11,0.4); color: white; }
        .alert { border-radius: 10px; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>Admin Login 👑</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <div class="mb-3"><input type="text" class="form-control" name="username" placeholder="Username" required></div>
            <div class="mb-3"><input type="password" class="form-control" name="password" placeholder="Password" required></div>
            <button type="submit" class="btn btn-login">Login <i class="fas fa-sign-in-alt ms-2"></i></button>
        </form>
        <div class="text-center mt-3"><a href="/" style="color: #FF8C00; text-decoration: none;">← Back to Portfolio</a></div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

ADMIN_DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - Virat King</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: #0a0a0a; color: white; font-family: 'Poppins', sans-serif; }
        .navbar { background: rgba(10,10,10,0.95); border-bottom: 1px solid rgba(244,50,11,0.3); }
        .brand { background: linear-gradient(135deg, #F4320B, #FF1493, #FF8C00); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 1.5rem; font-weight: 700; text-decoration: none; }
        .card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 15px; padding: 25px; margin-bottom: 20px; }
        .stat-card { text-align: center; }
        .stat-card i { font-size: 2.5rem; margin-bottom: 10px; background: linear-gradient(135deg, #F4320B, #FF8C00); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stat-card h3 { font-size: 2rem; font-weight: 700; }
        .table { color: white; }
        .table th { border-color: rgba(255,255,255,0.1); color: #FF8C00; }
        .table td { border-color: rgba(255,255,255,0.1); }
        .btn-sm { padding: 5px 15px; border-radius: 20px; font-size: 0.8rem; }
        .badge-read { background: #32CD32; }
        .badge-unread { background: #F4320B; }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="container">
            <a href="/admin" class="brand">Virat King Admin 👑</a>
            <div>
                <a href="/" class="btn btn-outline-light btn-sm me-2">View Site</a>
                <a href="/admin/logout" class="btn btn-outline-danger btn-sm">Logout</a>
            </div>
        </div>
    </nav>
    <div class="container py-5">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show">{{ message }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <h2 class="mb-4">Dashboard</h2>
        <div class="row mb-4">
            <div class="col-md-4"><div class="card stat-card"><i class="fas fa-envelope"></i><h3>{{ total_contacts }}</h3><p>Total Messages</p></div></div>
            <div class="col-md-4"><div class="card stat-card"><i class="fas fa-envelope-open"></i><h3>{{ unread_contacts }}</h3><p>Unread Messages</p></div></div>
            <div class="col-md-4"><div class="card stat-card"><i class="fas fa-eye"></i><h3>{{ total_visits }}</h3><p>Site Visits</p></div></div>
        </div>
        
        <h3 class="mb-3">Recent Messages</h3>
        <div class="card">
            <div class="table-responsive">
                <table class="table">
                    <thead><tr><th>Name</th><th>Email</th><th>Subject</th><th>Date</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody>
                        {% for contact in recent_contacts %}
                        <tr>
                            <td>{{ contact.name }}</td>
                            <td>{{ contact.email }}</td>
                            <td>{{ contact.subject or 'N/A' }}</td>
                            <td>{{ contact.created_at[:10] }}</td>
                            <td><span class="badge {{ 'badge-read' if contact.is_read else 'badge-unread' }}">{{ 'Read' if contact.is_read else 'Unread' }}</span></td>
                            <td>
                                <a href="/admin/contacts/{{ contact.id }}/read" class="btn btn-success btn-sm">Mark Read</a>
                                <a href="/admin/contacts/{{ contact.id }}/delete" class="btn btn-danger btn-sm" onclick="return confirm('Delete?')">Delete</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        <a href="/admin/contacts" class="btn btn-gradient mt-3" style="background: linear-gradient(135deg, #F4320B, #FF8C00); color: white; border: none; padding: 10px 30px; border-radius: 50px;">View All Messages</a>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

ADMIN_CONTACTS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>All Contacts - Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: #0a0a0a; color: white; font-family: 'Poppins', sans-serif; }
        .navbar { background: rgba(10,10,10,0.95); border-bottom: 1px solid rgba(244,50,11,0.3); }
        .brand { background: linear-gradient(135deg, #F4320B, #FF1493, #FF8C00); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 1.5rem; font-weight: 700; text-decoration: none; }
        .card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 15px; padding: 25px; }
        .table { color: white; }
        .table th { border-color: rgba(255,255,255,0.1); color: #FF8C00; }
        .table td { border-color: rgba(255,255,255,0.1); }
        .badge-read { background: #32CD32; }
        .badge-unread { background: #F4320B; }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="container">
            <a href="/admin" class="brand">← Back to Dashboard</a>
            <a href="/admin/logout" class="btn btn-outline-danger btn-sm">Logout</a>
        </div>
    </nav>
    <div class="container py-5">
        <h2 class="mb-4">All Messages ({{ contacts|length }})</h2>
        <div class="card">
            <div class="table-responsive">
                <table class="table">
                    <thead><tr><th>#</th><th>Name</th><th>Email</th><th>Phone</th><th>Subject</th><th>Message</th><th>Date</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody>
                        {% for contact in contacts %}
                        <tr>
                            <td>{{ contact.id }}</td>
                            <td>{{ contact.name }}</td>
                            <td>{{ contact.email }}</td>
                            <td>{{ contact.phone or 'N/A' }}</td>
                            <td>{{ contact.subject or 'N/A' }}</td>
                            <td>{{ contact.message[:50] }}...</td>
                            <td>{{ contact.created_at[:10] }}</td>
                            <td><span class="badge {{ 'badge-read' if contact.is_read else 'badge-unread' }}">{{ 'Read' if contact.is_read else 'Unread' }}</span></td>
                            <td>
                                <a href="/admin/contacts/{{ contact.id }}/read" class="btn btn-success btn-sm">Read</a>
                                <a href="/admin/contacts/{{ contact.id }}/delete" class="btn btn-danger btn-sm" onclick="return confirm('Delete?')">Delete</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''


# ==================== ROUTES ====================

@app.route('/')
def home():
    """Home page route"""
    return render_template_string(INDEX_TEMPLATE)


@app.route('/submit-contact', methods=['POST'])
def submit_contact():
    """Handle contact form submission"""
    try:
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        errors = []
        if not name: errors.append('Name is required')
        if not email: errors.append('Email is required')
        elif '@' not in email: errors.append('Invalid email address')
        if not message: errors.append('Message is required')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return redirect(url_for('home', _anchor='contact'))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO contacts (name, email, phone, subject, message) VALUES (?, ?, ?, ?, ?)',
                      (name, email, phone, subject, message))
        conn.commit()
        conn.close()
        
        flash('✅ Thank you! Your message has been sent successfully. I will get back to you soon!', 'success')
        return redirect(url_for('home', _anchor='contact'))
        
    except Exception as e:
        print(f"Error: {e}")
        flash('❌ An error occurred. Please try again later.', 'error')
        return redirect(url_for('home', _anchor='contact'))


@app.route('/api/contacts')
def get_contacts_api():
    """API endpoint"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM contacts ORDER BY created_at DESC')
    contacts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(contacts)


@app.route('/track-visit', methods=['POST'])
def track_visit():
    """Track visits"""
    try:
        data = request.get_json()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO site_visits (ip_address, user_agent, page_visited) VALUES (?, ?, ?)',
                      (request.remote_addr, request.user_agent.string, data.get('page', 'home')))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except:
        return jsonify({'status': 'error'})


# ==================== ADMIN ROUTES ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Please login to access admin panel.', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/admin')
@login_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM contacts')
    total_contacts = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM contacts WHERE is_read = 0')
    unread_contacts = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM site_visits')
    total_visits = cursor.fetchone()[0]
    cursor.execute('SELECT * FROM contacts ORDER BY created_at DESC LIMIT 10')
    recent_contacts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template_string(ADMIN_DASHBOARD_TEMPLATE,
                                 total_contacts=total_contacts,
                                 unread_contacts=unread_contacts,
                                 total_visits=total_visits,
                                 recent_contacts=recent_contacts)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM admin_users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            session['admin_username'] = username
            flash('Welcome back, Admin! 👑', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template_string(ADMIN_LOGIN_TEMPLATE)


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin/contacts')
@login_required
def admin_contacts():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM contacts ORDER BY created_at DESC')
    contacts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return render_template_string(ADMIN_CONTACTS_TEMPLATE, contacts=contacts)


@app.route('/admin/contacts/<int:contact_id>/read')
@login_required
def mark_contact_read(contact_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE contacts SET is_read = 1 WHERE id = ?', (contact_id,))
    conn.commit()
    conn.close()
    flash('Contact marked as read.', 'success')
    return redirect(url_for('admin_contacts'))


@app.route('/admin/contacts/<int:contact_id>/delete')
@login_required
def delete_contact(contact_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM contacts WHERE id = ?', (contact_id,))
    conn.commit()
    conn.close()
    flash('Contact deleted.', 'success')
    return redirect(url_for('admin_contacts'))


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template_string('<html><body style="background:#0a0a0a;color:white;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;"><div style="text-align:center;"><h1 style="font-size:5rem;background:linear-gradient(135deg,#F4320B,#FF1493,#FF8C00);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">404</h1><p>Page Not Found</p><a href="/" style="color:#FF8C00;">Go Home</a></div></body></html>'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template_string('<html><body style="background:#0a0a0a;color:white;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;"><div style="text-align:center;"><h1 style="font-size:5rem;background:linear-gradient(135deg,#F4320B,#FF1493,#FF8C00);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">500</h1><p>Internal Server Error</p><a href="/" style="color:#FF8C00;">Go Home</a></div></body></html>'), 500


# ==================== MAIN ====================

if __name__ == '__main__':
    with app.app_context():
        init_db()
        insert_sample_data()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)