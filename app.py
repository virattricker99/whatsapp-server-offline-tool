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
    print(" Database initialized successfully!")


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
        ''', ('admin', default_password, 'viratking1978@gmail.com'))
        conn.commit()
        print(" Default admin created!")
    
    conn.close()


# ==================== ULTRA PREMIUM HTML TEMPLATE ====================

INDEX_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Virat King - Professional Software Developer & Full Stack Web Developer Portfolio">
    <meta name="keywords" content="software developer, web developer, full stack, python, flask, virat king">
    <meta name="author" content="Virat King">
    <title>Virat King  | Software Developer & Web Developer</title>
    
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://unpkg.com/aos@2.3.1/dist/aos.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&family=Orbitron:wght@400;700;900&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
    
    <style>
        :root {
            --navy-dark: #0A0E27;
            --navy: #0F1535;
            --navy-light: #1A2150;
            --navy-lighter: #252D6B;
            --orange-dark: #E65100;
            --orange: #FF6D00;
            --orange-light: #FF9100;
            --orange-bright: #FFAB40;
            --gold: #FFD700;
            --gold-light: #FFE082;
            --white: #FFFFFF;
            --text-primary: #E8EAF6;
            --text-secondary: #B0BEC5;
            --glass-bg: rgba(15, 21, 53, 0.6);
            --glass-border: rgba(255, 109, 0, 0.3);
            --card-bg: rgba(26, 33, 80, 0.7);
            --card-hover: rgba(37, 45, 107, 0.8);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Poppins', sans-serif;
            background: var(--navy-dark);
            color: var(--text-primary);
            overflow-x: hidden;
            cursor: default;
        }

        /* Custom Scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--navy-dark); }
        ::-webkit-scrollbar-thumb { background: linear-gradient(180deg, var(--orange-dark), var(--orange-bright)); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: linear-gradient(180deg, var(--orange), var(--gold)); }

        /* Animated Stars Background */
        .stars-container {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            z-index: -2; overflow: hidden;
        }
        .star {
            position: absolute; background: white; border-radius: 50%;
            animation: twinkle var(--duration) ease-in-out infinite;
            animation-delay: var(--delay);
        }
        @keyframes twinkle {
            0%, 100% { opacity: 0.3; transform: scale(1); }
            50% { opacity: 1; transform: scale(1.8); }
        }

        /* Gradient Background */
        .gradient-bg {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -3;
            background: radial-gradient(ellipse at top left, rgba(255,109,0,0.08) 0%, transparent 50%),
                        radial-gradient(ellipse at bottom right, rgba(255,215,0,0.06) 0%, transparent 50%),
                        radial-gradient(ellipse at center, rgba(26,33,80,0.4) 0%, transparent 70%),
                        linear-gradient(180deg, #0A0E27 0%, #0F1535 30%, #1A2150 60%, #0F1535 100%);
            animation: bgShift 15s ease infinite;
        }
        @keyframes bgShift {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.9; }
        }

        /* Floating Orbs */
        .orb-container { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; overflow: hidden; pointer-events: none; }
        .orb {
            position: absolute; border-radius: 50%; filter: blur(100px); opacity: 0.12;
            animation: orbFloat 25s infinite ease-in-out;
        }
        .orb-1 { width: 500px; height: 500px; background: var(--orange); top: -150px; left: -150px; animation-delay: 0s; }
        .orb-2 { width: 400px; height: 400px; background: var(--gold); bottom: -100px; right: -100px; animation-delay: -8s; }
        .orb-3 { width: 350px; height: 350px; background: var(--navy-lighter); top: 50%; left: 50%; transform: translate(-50%, -50%); animation-delay: -16s; }
        @keyframes orbFloat {
            0%, 100% { transform: translate(0, 0) scale(1); }
            25% { transform: translate(80px, -60px) scale(1.15); }
            50% { transform: translate(-40px, 80px) scale(0.9); }
            75% { transform: translate(-80px, -40px) scale(1.1); }
        }

        /* Premium Loading Screen */
        #loading-screen {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: var(--navy-dark); display: flex; flex-direction: column;
            align-items: center; justify-content: center; z-index: 10000;
            transition: opacity 0.6s ease, visibility 0.6s ease;
        }
        .loader-logo {
            font-family: 'Orbitron', sans-serif; font-size: 2.5rem; font-weight: 900;
            background: linear-gradient(135deg, var(--orange-bright), var(--gold), var(--orange));
            -webkit-background-clip: text; background-clip: text;
            -webkit-text-fill-color: transparent; margin-bottom: 30px;
            animation: logoPulse 1.5s ease-in-out infinite;
        }
        @keyframes logoPulse {
            0%, 100% { transform: scale(1); filter: brightness(1); }
            50% { transform: scale(1.08); filter: brightness(1.3); }
        }
        .loader-ring {
            width: 80px; height: 80px; position: relative;
        }
        .loader-ring div {
            position: absolute; width: 100%; height: 100%;
            border-radius: 50%; border: 3px solid transparent;
            animation: ringSpin 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
        }
        .loader-ring div:nth-child(1) { border-top-color: var(--orange); animation-delay: -0.45s; }
        .loader-ring div:nth-child(2) { border-right-color: var(--gold); animation-delay: -0.3s; }
        .loader-ring div:nth-child(3) { border-bottom-color: var(--orange-light); animation-delay: -0.15s; }
        .loader-ring div:nth-child(4) { border-left-color: var(--orange-bright); }
        @keyframes ringSpin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Scroll Progress Bar */
        .scroll-progress {
            position: fixed; top: 0; left: 0; height: 3px;
            background: linear-gradient(90deg, var(--orange-dark), var(--orange-bright), var(--gold));
            z-index: 9999; transition: width 0.1s ease;
            box-shadow: 0 0 15px rgba(255,109,0,0.6), 0 0 30px rgba(255,215,0,0.3);
        }

        /* Premium Navigation */
        .navbar {
            background: rgba(10, 14, 39, 0.85); backdrop-filter: blur(30px);
            padding: 15px 0; transition: all 0.4s ease;
            border-bottom: 1px solid rgba(255, 109, 0, 0.2);
        }
        .navbar.scrolled {
            padding: 10px 0;
            box-shadow: 0 5px 40px rgba(255, 109, 0, 0.2);
            border-bottom: 1px solid rgba(255, 215, 0, 0.3);
            background: rgba(10, 14, 39, 0.95);
        }
        .brand-text {
            font-family: 'Orbitron', sans-serif; font-size: 26px; font-weight: 900;
            background: linear-gradient(135deg, var(--orange-bright), var(--gold));
            -webkit-background-clip: text; background-clip: text;
            -webkit-text-fill-color: transparent; text-decoration: none;
            letter-spacing: 1px;
        }
        .brand-crown { -webkit-text-fill-color: var(--gold); font-size: 22px; }
        .nav-link {
            color: var(--text-primary) !important; margin: 0 8px;
            font-weight: 500; font-size: 0.95rem; position: relative;
            transition: all 0.3s ease; letter-spacing: 0.5px;
        }
        .nav-link::after {
            content: ''; position: absolute; bottom: -5px; left: 50%; transform: translateX(-50%);
            width: 0; height: 2px; background: linear-gradient(90deg, var(--orange), var(--gold));
            transition: width 0.3s ease; border-radius: 2px;
        }
        .nav-link:hover { color: var(--orange-bright) !important; }
        .nav-link:hover::after { width: 80%; }

        /* Hero Section */
        .hero-section {
            position: relative; min-height: 100vh; display: flex;
            align-items: center; overflow: hidden; padding-top: 80px;
        }
        .hero-badge {
            display: inline-block; background: rgba(255,109,0,0.15);
            border: 1px solid rgba(255,109,0,0.4); color: var(--orange-bright);
            padding: 8px 25px; border-radius: 50px; font-size: 0.9rem;
            font-weight: 600; letter-spacing: 3px; margin-bottom: 20px;
            animation: badgeGlow 3s ease-in-out infinite;
        }
        @keyframes badgeGlow {
            0%, 100% { box-shadow: 0 0 10px rgba(255,109,0,0.3); }
            50% { box-shadow: 0 0 30px rgba(255,109,0,0.6), 0 0 60px rgba(255,215,0,0.2); }
        }
        .hero-title {
            font-size: 4rem; font-weight: 800; margin-bottom: 15px;
            line-height: 1.1; color: var(--white);
        }
        .hero-title .highlight {
            background: linear-gradient(135deg, var(--orange), var(--gold), var(--orange-bright));
            -webkit-background-clip: text; background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .typing-wrapper {
            font-size: 1.8rem; font-weight: 600; margin-bottom: 20px;
            min-height: 45px; color: var(--orange-light);
        }
        .typing-cursor { animation: blink 0.7s infinite; color: var(--gold); }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        .hero-desc {
            font-size: 1.1rem; color: var(--text-secondary); margin-bottom: 35px;
            line-height: 1.8; max-width: 550px;
        }
        .hero-buttons { display: flex; flex-wrap: wrap; gap: 15px; }
        .btn-premium {
            padding: 14px 35px; border-radius: 50px; font-weight: 600;
            font-size: 1rem; letter-spacing: 0.5px; transition: all 0.4s ease;
            position: relative; overflow: hidden; z-index: 1; text-decoration: none;
            display: inline-flex; align-items: center; gap: 8px;
        }
        .btn-primary-gold {
            background: linear-gradient(135deg, var(--orange-dark), var(--orange), var(--orange-light));
            color: white; border: none;
            box-shadow: 0 5px 25px rgba(255,109,0,0.3);
        }
        .btn-primary-gold::before {
            content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%;
            background: linear-gradient(135deg, var(--orange-light), var(--gold), var(--orange));
            transition: left 0.5s ease; z-index: -1;
        }
        .btn-primary-gold:hover::before { left: 0; }
        .btn-primary-gold:hover {
            transform: translateY(-4px);
            box-shadow: 0 15px 45px rgba(255,109,0,0.5);
            color: white;
        }
        .btn-outline-premium {
            border: 2px solid rgba(255,215,0,0.4); color: var(--text-primary);
            background: transparent;
        }
        .btn-outline-premium:hover {
            background: rgba(255,215,0,0.1); border-color: var(--gold);
            transform: translateY(-4px); color: var(--gold);
            box-shadow: 0 10px 35px rgba(255,215,0,0.2);
        }

        /* Hero Image */
        .hero-image-wrap {
            position: relative; display: flex; justify-content: center; align-items: center;
        }
        .hero-img-ring {
            width: 370px; height: 370px; border-radius: 50%; padding: 6px;
            background: linear-gradient(135deg, var(--orange-dark), var(--gold), var(--orange-bright));
            animation: floatImg 4s ease-in-out infinite, rotateBorder 8s linear infinite;
            box-shadow: 0 0 40px rgba(255,109,0,0.3), 0 0 80px rgba(255,215,0,0.2), 0 0 120px rgba(255,109,0,0.1);
        }
        @keyframes floatImg {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-25px); }
        }
        @keyframes rotateBorder {
            0% { filter: hue-rotate(0deg); }
            100% { filter: hue-rotate(30deg); }
        }
        .hero-img {
            width: 100%; height: 100%; border-radius: 50%; object-fit: cover;
            border: 5px solid var(--navy-dark);
        }
        .hero-img-glow {
            position: absolute; width: 390px; height: 390px; border-radius: 50%;
            background: transparent;
            box-shadow: 0 0 80px rgba(255,109,0,0.15), 0 0 150px rgba(255,215,0,0.1);
            pointer-events: none;
        }

        /* Social Icons */
        .social-icons { display: flex; gap: 15px; margin-top: 25px; }
        .social-icon {
            width: 48px; height: 48px; border-radius: 50%;
            background: var(--glass-bg); border: 1px solid var(--glass-border);
            display: flex; align-items: center; justify-content: center;
            color: var(--text-primary); font-size: 1.2rem;
            transition: all 0.4s ease; text-decoration: none; position: relative; overflow: hidden;
        }
        .social-icon::before {
            content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(135deg, var(--orange), var(--gold));
            opacity: 0; transition: opacity 0.4s ease; border-radius: 50%;
        }
        .social-icon:hover::before { opacity: 1; }
        .social-icon i { position: relative; z-index: 1; transition: all 0.4s ease; }
        .social-icon:hover { transform: translateY(-8px); border-color: transparent; box-shadow: 0 15px 40px rgba(255,109,0,0.4); color: white; }
        .social-icon:hover i { transform: scale(1.2); }

        /* Glass Card */
        .glass-card {
            background: var(--card-bg); border: 1px solid var(--glass-border);
            border-radius: 24px; padding: 35px; backdrop-filter: blur(20px);
            transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative; overflow: hidden;
        }
        .glass-card::before {
            content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.03), transparent);
            transition: left 0.6s ease;
        }
        .glass-card:hover::before { left: 100%; }
        .glass-card:hover {
            transform: translateY(-12px);
            background: var(--card-hover);
            border-color: rgba(255,215,0,0.4);
            box-shadow: 0 25px 70px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,215,0,0.15);
        }

        /* Section Styles */
        section { padding: 100px 0; position: relative; }
        .section-header { text-align: center; margin-bottom: 70px; }
        .section-badge {
            display: inline-block; font-family: 'Rajdhani', sans-serif;
            font-size: 0.95rem; font-weight: 700; letter-spacing: 4px;
            color: var(--orange-bright); margin-bottom: 15px;
            text-transform: uppercase;
        }
        .section-title {
            font-size: 2.8rem; font-weight: 800; color: var(--white); margin-bottom: 15px;
        }
        .section-title .gold { background: linear-gradient(135deg, var(--orange-bright), var(--gold)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
        .section-line {
            width: 80px; height: 4px; background: linear-gradient(90deg, var(--orange), var(--gold));
            margin: 0 auto 20px; border-radius: 2px;
        }
        .section-subtitle { color: var(--text-secondary); font-size: 1.1rem; max-width: 600px; margin: 0 auto; }

        /* About Section */
        .about-img-wrap {
            border-radius: 24px; overflow: hidden; border: 3px solid rgba(255,109,0,0.3);
            box-shadow: 0 15px 50px rgba(0,0,0,0.4);
            transition: all 0.5s ease;
        }
        .about-img-wrap:hover {
            border-color: rgba(255,215,0,0.5);
            box-shadow: 0 20px 60px rgba(255,109,0,0.2);
        }
        .about-img-wrap img { width: 100%; height: auto; display: block; }
        .about-content h3 {
            background: linear-gradient(135deg, var(--orange-bright), var(--gold));
            -webkit-background-clip: text; background-clip: text;
            -webkit-text-fill-color: transparent; margin-bottom: 20px; font-size: 1.8rem;
        }
        .about-content p { color: var(--text-secondary); line-height: 1.9; font-size: 1.05rem; }
        .info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-top: 30px; }
        .info-card {
            text-align: center; padding: 25px 20px; border-radius: 20px;
            background: var(--card-bg); border: 1px solid var(--glass-border);
            transition: all 0.4s ease;
        }
        .info-card i { font-size: 2rem; margin-bottom: 12px; background: linear-gradient(135deg, var(--orange), var(--gold)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
        .info-card h4 { color: var(--white); font-size: 1rem; margin-bottom: 5px; }
        .info-card p { color: var(--text-secondary); font-size: 0.9rem; margin: 0; }
        .info-card:hover { transform: translateY(-8px); box-shadow: 0 15px 40px rgba(255,109,0,0.15); border-color: rgba(255,215,0,0.3); }

        /* Skills */
        .skills-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; }
        .skill-card {
            text-align: center; padding: 30px 20px; border-radius: 20px;
            background: var(--card-bg); border: 1px solid var(--glass-border);
            transition: all 0.4s ease;
        }
        .skill-card i { font-size: 2.8rem; margin-bottom: 15px; transition: all 0.4s ease; }
        .skill-card h4 { color: var(--white); font-size: 1rem; margin-bottom: 12px; }
        .skill-progress {
            height: 6px; background: rgba(255,255,255,0.1); border-radius: 10px; overflow: hidden;
        }
        .skill-progress-bar {
            height: 100%; border-radius: 10px; font-size: 0.65rem; line-height: 6px;
            color: white; text-align: right; padding-right: 5px;
            transition: width 2s ease;
        }
        .skill-card:hover { transform: translateY(-10px); box-shadow: 0 20px 50px rgba(0,0,0,0.4); border-color: rgba(255,215,0,0.3); }
        .skill-card:hover i { transform: scale(1.2); }

        /* Services */
        .services-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 25px; }
        .service-card {
            text-align: center; padding: 45px 30px; border-radius: 24px;
            background: var(--card-bg); border: 1px solid var(--glass-border);
            transition: all 0.5s ease; position: relative; overflow: hidden;
        }
        .service-card .service-icon {
            font-size: 3.5rem; margin-bottom: 20px;
            background: linear-gradient(135deg, var(--orange), var(--gold));
            -webkit-background-clip: text; background-clip: text;
            -webkit-text-fill-color: transparent; transition: all 0.5s ease;
        }
        .service-card h3 { color: var(--white); font-size: 1.3rem; margin-bottom: 12px; }
        .service-card p { color: var(--text-secondary); line-height: 1.7; font-size: 0.95rem; }
        .service-card:hover { transform: translateY(-15px); box-shadow: 0 30px 70px rgba(0,0,0,0.5); border-color: rgba(255,215,0,0.4); }
        .service-card:hover .service-icon { transform: scale(1.2) rotate(10deg); }

        /* Timeline */
        .timeline { position: relative; padding: 30px 0; }
        .timeline::before {
            content: ''; position: absolute; left: 50%; top: 0; bottom: 0; width: 3px;
            background: linear-gradient(180deg, var(--orange-dark), var(--gold), var(--orange-bright));
            transform: translateX(-50%); border-radius: 3px;
            box-shadow: 0 0 20px rgba(255,109,0,0.3);
        }
        .timeline-item { margin-bottom: 50px; position: relative; width: 50%; }
        .timeline-item:nth-child(odd) { left: 0; padding-right: 50px; }
        .timeline-item:nth-child(even) { left: 50%; padding-left: 50px; }
        .timeline-dot {
            position: absolute; top: 20px; width: 18px; height: 18px;
            background: var(--gold); border-radius: 50%; z-index: 2;
            box-shadow: 0 0 15px rgba(255,215,0,0.6);
        }
        .timeline-item:nth-child(odd) .timeline-dot { right: -9px; }
        .timeline-item:nth-child(even) .timeline-dot { left: -9px; }
        .timeline-content { padding: 30px; }
        .timeline-year {
            display: inline-block; background: linear-gradient(135deg, var(--orange), var(--orange-light));
            color: white; padding: 6px 22px; border-radius: 50px; font-size: 0.9rem;
            font-weight: 600; margin-bottom: 15px; letter-spacing: 1px;
        }
        .timeline-content h3 { color: var(--white); margin-bottom: 10px; font-size: 1.2rem; }
        .timeline-content p { color: var(--text-secondary); margin: 0; line-height: 1.7; }

        /* Contact */
        .contact-info-item {
            display: flex; align-items: center; margin-bottom: 20px; padding: 22px;
            background: var(--card-bg); border-radius: 18px; border: 1px solid var(--glass-border);
            transition: all 0.4s ease;
        }
        .contact-info-item:hover { border-color: rgba(255,215,0,0.4); transform: translateX(8px); box-shadow: 0 10px 30px rgba(255,109,0,0.15); }
        .contact-icon {
            width: 55px; height: 55px; min-width: 55px; border-radius: 50%;
            background: linear-gradient(135deg, var(--orange), var(--orange-light));
            display: flex; align-items: center; justify-content: center;
            margin-right: 18px; font-size: 1.3rem; color: white;
        }
        .contact-info-item h5 { color: var(--white); margin-bottom: 4px; font-size: 1rem; }
        .contact-info-item p, .contact-info-item a { color: var(--text-secondary); margin: 0; text-decoration: none; font-size: 0.9rem; }

        .contact-form .form-control {
            background: var(--card-bg); border: 1px solid var(--glass-border);
            color: var(--white); padding: 14px 20px; border-radius: 14px;
            transition: all 0.3s ease; font-size: 0.95rem;
        }
        .contact-form .form-control:focus {
            background: rgba(37, 45, 107, 0.8); border-color: var(--orange);
            box-shadow: 0 0 0 4px rgba(255,109,0,0.1); color: white;
        }
        .contact-form .form-control::placeholder { color: var(--text-secondary); }

        /* Footer */
        .footer {
            background: linear-gradient(180deg, var(--navy-dark), #080C20);
            padding: 60px 0 30px; text-align: center;
            border-top: 1px solid rgba(255,109,0,0.2); position: relative;
        }
        .footer::before {
            content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
            background: linear-gradient(90deg, transparent, var(--orange), var(--gold), var(--orange-bright), transparent);
        }
        .footer h3 {
            font-family: 'Orbitron', sans-serif; font-size: 1.6rem;
            background: linear-gradient(135deg, var(--orange-bright), var(--gold));
            -webkit-background-clip: text; background-clip: text;
            -webkit-text-fill-color: transparent; margin-bottom: 10px;
        }
        .footer .subtitle { color: var(--orange-light); font-weight: 600; margin-bottom: 20px; letter-spacing: 1px; }
        .footer-social { display: flex; justify-content: center; gap: 15px; margin-bottom: 25px; }
        .footer-social a {
            width: 45px; height: 45px; border-radius: 50%; background: var(--card-bg);
            border: 1px solid var(--glass-border); display: flex; align-items: center;
            justify-content: center; color: var(--text-primary); transition: all 0.4s ease; text-decoration: none;
        }
        .footer-social a:hover { background: linear-gradient(135deg, var(--orange), var(--gold)); transform: translateY(-6px); box-shadow: 0 12px 35px rgba(255,109,0,0.4); color: white; border-color: transparent; }
        .copyright { color: var(--text-secondary); font-size: 0.9rem; margin-top: 20px; }
        .powered { margin-top: 12px; font-size: 0.85rem; background: linear-gradient(135deg, var(--orange), var(--gold)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
        .heart { color: #FF1493; animation: heartbeat 1.5s infinite; display: inline-block; -webkit-text-fill-color: #FF1493; }
        @keyframes heartbeat { 0%,100%{transform:scale(1)}15%{transform:scale(1.3)}30%{transform:scale(1)} }

        /* Scroll to Top */
        .scroll-top-btn {
            position: fixed; bottom: 35px; right: 35px; width: 55px; height: 55px;
            background: linear-gradient(135deg, var(--orange), var(--orange-light));
            border: none; border-radius: 50%; color: white; display: none;
            align-items: center; justify-content: center; z-index: 999;
            cursor: pointer; font-size: 1.3rem; box-shadow: 0 8px 35px rgba(255,109,0,0.5);
            animation: btnPulse 2.5s infinite; transition: all 0.3s ease;
        }
        .scroll-top-btn:hover { transform: scale(1.1); }
        @keyframes btnPulse {
            0% { box-shadow: 0 0 0 0 rgba(255,109,0,0.6); }
            70% { box-shadow: 0 0 0 25px rgba(255,109,0,0); }
            100% { box-shadow: 0 0 0 0 rgba(255,109,0,0); }
        }

        /* WhatsApp Float */
        .whatsapp-float {
            position: fixed; bottom: 110px; right: 35px; width: 60px; height: 60px;
            background: #25D366; border-radius: 50%; display: flex; align-items: center;
            justify-content: center; color: white; font-size: 2rem; z-index: 999;
            text-decoration: none; box-shadow: 0 8px 35px rgba(37,211,102,0.5);
            animation: btnPulse 2.5s infinite 0.5s; transition: all 0.3s ease;
        }
        .whatsapp-float:hover { transform: scale(1.15); color: white; }

        /* Alert Messages */
        .alert-premium { border-radius: 14px; padding: 16px 22px; margin-bottom: 20px; border: none; }
        .alert-success { background: rgba(50,205,50,0.15); color: #4ade80; border: 1px solid rgba(50,205,50,0.3); }
        .alert-error { background: rgba(255,109,0,0.15); color: var(--orange-bright); border: 1px solid rgba(255,109,0,0.3); }

        /* Responsive */
        @media (max-width: 992px) {
            .hero-title { font-size: 2.8rem; }
            .typing-wrapper { font-size: 1.4rem; }
            .hero-img-ring { width: 280px; height: 280px; margin-top: 40px; }
            .hero-img-glow { width: 300px; height: 300px; }
        }
        @media (max-width: 768px) {
            .hero-title { font-size: 2.2rem; }
            .typing-wrapper { font-size: 1.2rem; }
            .hero-img-ring { width: 230px; height: 230px; }
            .hero-img-glow { width: 250px; height: 250px; }
            .timeline::before { left: 25px; }
            .timeline-item { width: 100%; padding-left: 55px; padding-right: 0; }
            .timeline-item:nth-child(even) { left: 0; }
            .timeline-dot { left: 16px !important; }
            .section-title { font-size: 2rem; }
            .info-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <!-- Stars Background -->
    <div class="stars-container" id="starsContainer"></div>
    
    <!-- Gradient Background -->
    <div class="gradient-bg"></div>
    
    <!-- Floating Orbs -->
    <div class="orb-container">
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
    </div>

    <!-- Premium Loading Screen -->
    <div id="loading-screen">
        <div class="loader-logo">VIRAT KING </div>
        <div class="loader-ring">
            <div></div><div></div><div></div><div></div>
        </div>
    </div>

    <!-- Scroll Progress -->
    <div class="scroll-progress"></div>

    <!-- Premium Navigation -->
    <nav class="navbar navbar-expand-lg fixed-top">
        <div class="container">
            <a class="navbar-brand" href="#home">
                <span class="brand-text">Virat<span class="brand-crown"></span></span>
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" style="border-color: rgba(255,215,0,0.4);">
                <span class="navbar-toggler-icon" style="filter: invert(1);"></span>
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
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <section id="home" class="hero-section">
        <div class="container">
            <div class="row align-items-center min-vh-100">
                <div class="col-lg-7" data-aos="fade-right" data-aos-duration="1200">
                    <div class="hero-badge"> AVAILABLE FOR PROJECTS</div>
                    <h1 class="hero-title">Hi, I'm <span class="highlight">Virat King</span> </h1>
                    <div class="typing-wrapper">
                        <span id="typingText"></span><span class="typing-cursor">|</span>
                    </div>
                    <p class="hero-desc">
                        A passionate <strong style="color: var(--orange-bright);">Software Developer</strong> & 
                        <strong style="color: var(--gold);">Full Stack Web Developer</strong> crafting modern, 
                        high-performance digital solutions with cutting-edge technologies.
                    </p>
                    <div class="hero-buttons">
                        <a href="#contact" class="btn-premium btn-primary-gold">
                            <i class="fas fa-handshake"></i> Hire Me
                        </a>
                        <a href="#" class="btn-premium btn-outline-premium">
                            <i class="fas fa-download"></i> Resume
                        </a>
                        <a href="#contact" class="btn-premium btn-outline-premium">
                            <i class="fas fa-paper-plane"></i> Contact
                        </a>
                    </div>
                    <div class="social-icons">
                        <a href="https://www.instagram.com/offical_virat____0?igsh=MWk3OTNwbW5oamo3dA==" target="_blank" class="social-icon"><i class="fab fa-instagram"></i></a>
                        <a href="https://www.snapchat.com/add/viratking1000?share_id=BxdhBUhR1hg&locale=en-MM" target="_blank" class="social-icon"><i class="fab fa-snapchat"></i></a>
                        <a href="#" class="social-icon"><i class="fab fa-linkedin"></i></a>
                        <a href="#" class="social-icon"><i class="fab fa-github"></i></a>
                        <a href="mailto:viratking1978@gmail.com" class="social-icon"><i class="fas fa-envelope"></i></a>
                    </div>
                </div>
                <div class="col-lg-5 text-center" data-aos="fade-left" data-aos-duration="1200">
                    <div class="hero-image-wrap">
                        <div class="hero-img-glow"></div>
                        <div class="hero-img-ring">
                            <img src="https://i.ibb.co/xqw8J9PY/Screenshot-2026-07-13-18-15-26-72-92460851df6f172a4592fca41cc2d2e6.jpg" alt="Virat King" class="hero-img">
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- About Section -->
    <section id="about">
        <div class="container">
            <div class="section-header" data-aos="fade-up">
                <div class="section-badge">About Me</div>
                <h2 class="section-title">Get To <span class="gold">Know Me</span></h2>
                <div class="section-line"></div>
                <p class="section-subtitle">Passionate developer dedicated to creating exceptional digital experiences</p>
            </div>
            <div class="row align-items-center">
                <div class="col-lg-5 mb-4 mb-lg-0" data-aos="fade-right">
                    <div class="about-img-wrap">
                        <img src="https://i.ibb.co/xqw8J9PY/Screenshot-2026-07-13-18-15-26-72-92460851df6f172a4592fca41cc2d2e6.jpg" alt="Virat King">
                    </div>
                </div>
                <div class="col-lg-7" data-aos="fade-left">
                    <div class="about-content">
                        <h3>Professional Software Developer</h3>
                        <p>
                            Motivated and results-driven <strong style="color: var(--orange-bright);">Software Developer</strong> 
                            with expertise in modern web technologies. I specialize in building secure, scalable, and 
                            user-friendly applications. Proficient in HTML5, CSS3, JavaScript, Bootstrap 5, React.js, 
                            Node.js, Python Flask, SQLite, MySQL, Git & GitHub.
                        </p>
                        <div class="info-grid">
                            <div class="info-card">
                                <i class="fas fa-user-graduate"></i><h4>Qualification</h4><p>BCA + MCA</p>
                            </div>
                            <div class="info-card">
                                <i class="fas fa-briefcase"></i><h4>Experience</h4><p>Freelance Developer</p>
                            </div>
                            <div class="info-card">
                                <i class="fas fa-code"></i><h4>Specialization</h4><p>Full Stack Dev</p>
                            </div>
                            <div class="info-card">
                                <i class="fas fa-shield-alt"></i><h4>Focus</h4><p>Cybersecurity & AI</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Skills Section -->
    <section id="skills">
        <div class="container">
            <div class="section-header" data-aos="fade-up">
                <div class="section-badge">My Skills</div>
                <h2 class="section-title">Tech <span class="gold">Stack</span></h2>
                <div class="section-line"></div>
            </div>
            <div class="skills-grid" data-aos="fade-up">
                <div class="skill-card"><i class="fab fa-html5" style="color:#E44D26;"></i><h4>HTML5</h4><div class="skill-progress"><div class="skill-progress-bar" style="width:95%;background:linear-gradient(90deg,#E44D26,#F4320B);">95%</div></div></div>
                <div class="skill-card"><i class="fab fa-css3-alt" style="color:#1572B6;"></i><h4>CSS3</h4><div class="skill-progress"><div class="skill-progress-bar" style="width:90%;background:linear-gradient(90deg,#1572B6,#00BFFF);">90%</div></div></div>
                <div class="skill-card"><i class="fab fa-js" style="color:#F7DF1E;"></i><h4>JavaScript</h4><div class="skill-progress"><div class="skill-progress-bar" style="width:85%;background:linear-gradient(90deg,#F7DF1E,#FFD700);">85%</div></div></div>
                <div class="skill-card"><i class="fab fa-bootstrap" style="color:#7952B3;"></i><h4>Bootstrap 5</h4><div class="skill-progress"><div class="skill-progress-bar" style="width:90%;background:linear-gradient(90deg,#7952B3,#9400D3);">90%</div></div></div>
                <div class="skill-card"><i class="fab fa-react" style="color:#61DAFB;"></i><h4>React.js</h4><div class="skill-progress"><div class="skill-progress-bar" style="width:78%;background:linear-gradient(90deg,#61DAFB,#00BFFF);">78%</div></div></div>
                <div class="skill-card"><i class="fab fa-python" style="color:#3776AB;"></i><h4>Python</h4><div class="skill-progress"><div class="skill-progress-bar" style="width:88%;background:linear-gradient(90deg,#3776AB,#4169E1);">88%</div></div></div>
                <div class="skill-card"><i class="fas fa-flask"></i><h4>Flask</h4><div class="skill-progress"><div class="skill-progress-bar" style="width:85%;background:linear-gradient(90deg,#666,#2F4F4F);">85%</div></div></div>
                <div class="skill-card"><i class="fas fa-database" style="color:#4479A1;"></i><h4>MySQL/SQLite</h4><div class="skill-progress"><div class="skill-progress-bar" style="width:82%;background:linear-gradient(90deg,#4479A1,#003B57);">82%</div></div></div>
            </div>
        </div>
    </section>

    <!-- Services Section -->
    <section id="services">
        <div class="container">
            <div class="section-header" data-aos="fade-up">
                <div class="section-badge">Services</div>
                <h2 class="section-title">What I <span class="gold">Offer</span></h2>
                <div class="section-line"></div>
            </div>
            <div class="services-grid">
                <div class="service-card" data-aos="zoom-in"><div class="service-icon"><i class="fas fa-globe"></i></div><h3>Web Development</h3><p>Custom responsive websites with modern UI/UX.</p></div>
                <div class="service-card" data-aos="zoom-in" data-aos-delay="100"><div class="service-icon"><i class="fas fa-layer-group"></i></div><h3>Web Applications</h3><p>Scalable full-stack web applications.</p></div>
                <div class="service-card" data-aos="zoom-in" data-aos-delay="200"><div class="service-icon"><i class="fab fa-python"></i></div><h3>Python Development</h3><p>Backend APIs & automation solutions.</p></div>
                <div class="service-card" data-aos="zoom-in" data-aos-delay="300"><div class="service-icon"><i class="fas fa-file-code"></i></div><h3>Portfolio Sites</h3><p>Premium portfolio websites that stand out.</p></div>
            </div>
        </div>
    </section>

    <!-- Projects Section -->
    <section id="projects">
        <div class="container">
            <div class="section-header" data-aos="fade-up">
                <div class="section-badge">Projects</div>
                <h2 class="section-title">Featured <span class="gold">Work</span></h2>
                <div class="section-line"></div>
            </div>
            <div class="glass-card" data-aos="fade-up" style="overflow:hidden; padding:0;">
                <div class="row g-0">
                    <div class="col-lg-6">
                        <img src="https://via.placeholder.com/600x400/0F1535/FF9100?text=AI+Phishing+Detection+Tool" alt="Project" style="width:100%;height:100%;object-fit:cover;">
                    </div>
                    <div class="col-lg-6 p-4 p-lg-5">
                        <span class="badge" style="background:linear-gradient(135deg,var(--orange),var(--gold));color:white;padding:8px 20px;border-radius:50px;margin-bottom:15px;">Academic Project</span>
                        <h3 style="color:white;margin:15px 0;">AI-Based Phishing Detection Tool</h3>
                        <p style="color:var(--text-secondary);">Intelligent system that detects malicious websites and phishing attacks using ML algorithms.</p>
                        <div style="margin:15px 0;">
                            <span class="badge" style="background:rgba(255,109,0,0.2);color:var(--orange-bright);margin:3px;padding:6px 14px;border-radius:50px;">HTML5</span>
                            <span class="badge" style="background:rgba(255,109,0,0.2);color:var(--orange-bright);margin:3px;padding:6px 14px;border-radius:50px;">Python</span>
                            <span class="badge" style="background:rgba(255,109,0,0.2);color:var(--orange-bright);margin:3px;padding:6px 14px;border-radius:50px;">Flask</span>
                            <span class="badge" style="background:rgba(255,109,0,0.2);color:var(--orange-bright);margin:3px;padding:6px 14px;border-radius:50px;">ML</span>
                        </div>
                        <div style="display:flex;gap:10px;margin-top:20px;">
                            <a href="#" class="btn-premium btn-primary-gold"><i class="fas fa-external-link-alt"></i> Live Demo</a>
                            <a href="#" class="btn-premium btn-outline-premium"><i class="fab fa-github"></i> GitHub</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Education Section -->
    <section id="education">
        <div class="container">
            <div class="section-header" data-aos="fade-up">
                <div class="section-badge">Education</div>
                <h2 class="section-title">Academic <span class="gold">Journey</span></h2>
                <div class="section-line"></div>
            </div>
            <div class="timeline">
                <div class="timeline-item" data-aos="fade-right">
                    <div class="timeline-dot"></div>
                    <div class="timeline-content glass-card">
                        <div class="timeline-year">2020 - 2022</div>
                        <h3>12th (Science)</h3>
                        <p>Completed Higher Secondary Education with Science stream, building strong foundation in Mathematics, Physics, and Computer Science.</p>
                    </div>
                </div>
                <div class="timeline-item" data-aos="fade-left">
                    <div class="timeline-dot"></div>
                    <div class="timeline-content glass-card">
                        <div class="timeline-year">2022 - 2025</div>
                        <h3>Bachelor of Computer Applications (BCA)</h3>
                        <p>Focused on programming, web development, database management, software engineering, and modern application development.</p>
                    </div>
                </div>
                <div class="timeline-item" data-aos="fade-right">
                    <div class="timeline-dot"></div>
                    <div class="timeline-content glass-card">
                        <div class="timeline-year">2026 - 2028</div>
                        <h3>Master of Computer Applications (MCA)</h3>
                        <p>Advanced knowledge in full-stack development, cloud computing, cybersecurity, AI, and scalable software architecture.</p>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Contact Section -->
    <section id="contact">
        <div class="container">
            <div class="section-header" data-aos="fade-up">
                <div class="section-badge">Contact</div>
                <h2 class="section-title">Get In <span class="gold">Touch</span></h2>
                <div class="section-line"></div>
            </div>
            <div class="row">
                <div class="col-lg-5 mb-4 mb-lg-0" data-aos="fade-right">
                    <div class="contact-info-item"><div class="contact-icon"><i class="fas fa-phone"></i></div><div><h5>Phone</h5><p><a href="tel:+917310927827">+91 7310927827</a></p></div></div>
                    <div class="contact-info-item"><div class="contact-icon"><i class="fas fa-envelope"></i></div><div><h5>Email</h5><p><a href="mailto:viratking1978@gmail.com">viratking1978@gmail.com</a></p></div></div>
                    <div class="contact-info-item"><div class="contact-icon"><i class="fab fa-whatsapp"></i></div><div><h5>WhatsApp</h5><p><a href="https://wa.me/917310927827" target="_blank">Chat Now</a></p></div></div>
                    <div class="contact-info-item"><div class="contact-icon"><i class="fab fa-snapchat"></i></div><div><h5>Snapchat</h5><p><a href="https://www.snapchat.com/add/viratking1000" target="_blank">@viratking1000</a></p></div></div>
                    <div class="contact-info-item"><div class="contact-icon"><i class="fab fa-instagram"></i></div><div><h5>Instagram</h5><p><a href="https://www.instagram.com/offical_virat____0?igsh=MWk3OTNwbW5oamo3dA==" target="_blank">@offical_virat____0</a></p></div></div>
                </div>
                <div class="col-lg-7" data-aos="fade-left">
                    {% with messages = get_flashed_messages(with_categories=true) %}
                        {% if messages %}
                            {% for category, message in messages %}
                                <div class="alert-premium alert-{{ 'success' if category == 'success' else 'error' }} alert-dismissible fade show">
                                    {{ message }}
                                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="alert"></button>
                                </div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}
                    <form class="contact-form glass-card" action="{{ url_for('submit_contact') }}" method="POST">
                        <h3 style="color:white;margin-bottom:25px;">Send Me a Message </h3>
                        <div class="row">
                            <div class="col-md-6 mb-3"><input type="text" class="form-control" name="name" placeholder="Your Name *" required></div>
                            <div class="col-md-6 mb-3"><input type="email" class="form-control" name="email" placeholder="Your Email *" required></div>
                        </div>
                        <div class="mb-3"><input type="tel" class="form-control" name="phone" placeholder="Phone Number"></div>
                        <div class="mb-3"><input type="text" class="form-control" name="subject" placeholder="Subject"></div>
                        <div class="mb-3"><textarea class="form-control" name="message" rows="5" placeholder="Your Message *" required></textarea></div>
                        <button type="submit" class="btn-premium btn-primary-gold w-100" style="justify-content:center;">
                            <i class="fas fa-paper-plane"></i> Send Message
                        </button>
                    </form>
                </div>
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
        <div class="container">
            <h3>Made by Virat King </h3>
            <p class="subtitle">Software Developer & Full Stack Web Developer</p>
            <div class="footer-social">
                <a href="https://www.instagram.com/offical_virat____0?igsh=MWk3OTNwbW5oamo3dA==" target="_blank"><i class="fab fa-instagram"></i></a>
                <a href="https://www.snapchat.com/add/viratking1000" target="_blank"><i class="fab fa-snapchat"></i></a>
                <a href="#"><i class="fab fa-linkedin"></i></a>
                <a href="#"><i class="fab fa-github"></i></a>
                <a href="mailto:viratking1978@gmail.com"><i class="fas fa-envelope"></i></a>
            </div>
            <p class="copyright">© 2026 Virat King  | All Rights Reserved.</p>
            <p class="powered">Powered by <span style="-webkit-text-fill-color: var(--orange-bright);">Virat King</span> | Built with <span class="heart"></span> & Passion</p>
        </div>
    </footer>

    <!-- Scroll to Top -->
    <button class="scroll-top-btn" id="scrollTopBtn"><i class="fas fa-chevron-up"></i></button>

    <!-- WhatsApp Float -->
    <a href="https://wa.me/917310927827?text=Hi%20Virat%20King%20,%0A%0AI%20visited%20your%20portfolio%20website%20and%20I%20want%20to%20discuss%20a%20project%20with%20you!%0A%0AName:%0AProject%20Details:%0A%0ALooking%20forward%20to%20working%20with%20you!%20" class="whatsapp-float" target="_blank"><i class="fab fa-whatsapp"></i></a>

    <!-- Scripts -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://unpkg.com/aos@2.3.1/dist/aos.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        // Create Stars
        function createStars() {
            const container = document.getElementById('starsContainer');
            for (let i = 0; i < 150; i++) {
                const star = document.createElement('div');
                star.classList.add('star');
                star.style.left = Math.random() * 100 + '%';
                star.style.top = Math.random() * 100 + '%';
                star.style.width = Math.random() * 3 + 1 + 'px';
                star.style.height = star.style.width;
                star.style.setProperty('--duration', Math.random() * 3 + 2 + 's');
                star.style.setProperty('--delay', Math.random() * 5 + 's');
                container.appendChild(star);
            }
        }
        createStars();

        // Loading Screen
        $(window).on('load', function() {
            setTimeout(function() {
                $('#loading-screen').fadeOut(600);
            }, 2000);
        });

        // Initialize AOS
        AOS.init({ duration: 1000, once: true, offset: 80 });

        // Scroll Progress
        $(window).scroll(function() {
            var scroll = $(window).scrollTop();
            var height = $(document).height() - $(window).height();
            var progress = (scroll / height) * 100;
            $('.scroll-progress').css('width', progress + '%');
            
            if ($(window).scrollTop() > 50) {
                $('.navbar').addClass('scrolled');
            } else {
                $('.navbar').removeClass('scrolled');
            }

            if ($(window).scrollTop() > 500) {
                $('#scrollTopBtn').fadeIn();
            } else {
                $('#scrollTopBtn').fadeOut();
            }
        });

        // Smooth Scrolling
        $('a[href^="#"]').on('click', function(e) {
            e.preventDefault();
            var target = $(this.hash);
            if (target.length) {
                $('html, body').animate({ scrollTop: target.offset().top - 80 }, 800);
            }
        });

        // Typing Animation
        const texts = ['Software Developer', 'Full Stack Developer', 'Python Developer', 'Web Developer', 'Freelancer'];
        let textIdx = 0, charIdx = 0, deleting = false, speed = 100;

        function typeEffect() {
            const current = texts[textIdx];
            if (deleting) {
                $('#typingText').text(current.substring(0, charIdx - 1));
                charIdx--; speed = 50;
            } else {
                $('#typingText').text(current.substring(0, charIdx + 1));
                charIdx++; speed = 100;
            }
            if (!deleting && charIdx === current.length) { speed = 2000; deleting = true; }
            else if (deleting && charIdx === 0) { deleting = false; textIdx = (textIdx + 1) % texts.length; speed = 500; }
            setTimeout(typeEffect, speed);
        }
        typeEffect();

        // Scroll to Top
        $('#scrollTopBtn').on('click', function() {
            $('html, body').animate({ scrollTop: 0 }, 800);
        });

        // Track Visit
        $.ajax({ url: '/track-visit', type: 'POST', contentType: 'application/json', data: JSON.stringify({ page: 'home' }) });

        // Console Welcome
        console.log(`
        
           VIRAT KING  PORTFOLIO     
          Software Developer & Web Developer 
          Welcome to my premium portfolio!   
        
        `);
    </script>
</body>
</html>
'''

# ==================== ADMIN TEMPLATES ====================

ADMIN_LOGIN_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - Virat King</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{background:#0A0E27;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Poppins',sans-serif}
        .login-card{background:rgba(26,33,80,0.8);border:1px solid rgba(255,109,0,0.3);border-radius:24px;padding:45px;backdrop-filter:blur(20px);width:100%;max-width:420px;box-shadow:0 25px 70px rgba(0,0,0,0.4)}
        h2{background:linear-gradient(135deg,#FF9100,#FFD700);-webkit-background-clip:text;-webkit-text-fill-color:transparent;text-align:center;margin-bottom:35px;font-weight:800;font-size:2rem}
        .form-control{background:rgba(15,21,53,0.8);border:1px solid rgba(255,109,0,0.3);color:white;padding:14px;border-radius:14px;margin-bottom:18px}
        .form-control:focus{background:rgba(37,45,107,0.8);border-color:#FF9100;box-shadow:0 0 0 4px rgba(255,109,0,0.1);color:white}
        .btn-login{background:linear-gradient(135deg,#E65100,#FF6D00,#FF9100);color:white;border:none;padding:14px;border-radius:14px;width:100%;font-weight:700;font-size:1.1rem;letter-spacing:0.5px;transition:all 0.3s}
        .btn-login:hover{transform:translateY(-3px);box-shadow:0 15px 40px rgba(255,109,0,0.4)}
        .back-link{color:#FFAB40;text-decoration:none;display:block;text-align:center;margin-top:20px}
    </style>
</head>
<body>
    <div class="login-card">
        <h2>Admin Login </h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" style="border-radius:14px">
                        {{ message }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" class="form-control" name="username" placeholder="Username" required>
            <input type="password" class="form-control" name="password" placeholder="Password" required>
            <button type="submit" class="btn-login">Login <i class="fas fa-sign-in-alt ms-2"></i></button>
        </form>
        <a href="/" class="back-link"> Back to Portfolio</a>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

ADMIN_DASHBOARD_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body{background:#0A0E27;color:white;font-family:'Poppins',sans-serif}
        .navbar{background:rgba(10,14,39,0.95);border-bottom:1px solid rgba(255,109,0,0.3);padding:15px 0}
        .brand{background:linear-gradient(135deg,#FF9100,#FFD700);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:1.5rem;font-weight:800;text-decoration:none}
        .card{background:rgba(26,33,80,0.7);border:1px solid rgba(255,109,0,0.2);border-radius:20px;padding:25px;margin-bottom:25px}
        .stat-card{text-align:center}
        .stat-card i{font-size:2.5rem;margin-bottom:10px;background:linear-gradient(135deg,#FF6D00,#FFD700);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .stat-card h3{font-size:2.2rem;font-weight:800}
        .table{color:white}
        .table th{border-color:rgba(255,255,255,0.1);color:#FFAB40}
        .table td{border-color:rgba(255,255,255,0.1)}
        .badge-read{background:#4ade80}
        .badge-unread{background:#FF6D00}
        .btn-sm{padding:5px 15px;border-radius:20px;font-size:0.8rem}
    </style>
</head>
<body>
    <nav class="navbar"><div class="container"><a href="/admin" class="brand">Virat King Admin </a><div><a href="/" class="btn btn-outline-light btn-sm me-2">View Site</a><a href="/admin/logout" class="btn btn-outline-danger btn-sm">Logout</a></div></div></nav>
    <div class="container py-5">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show">{{ message }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <h2 class="mb-4">Dashboard Overview</h2>
        <div class="row mb-4">
            <div class="col-md-4"><div class="card stat-card"><i class="fas fa-envelope"></i><h3>{{ total_contacts }}</h3><p>Total Messages</p></div></div>
            <div class="col-md-4"><div class="card stat-card"><i class="fas fa-envelope-open"></i><h3>{{ unread_contacts }}</h3><p>Unread</p></div></div>
            <div class="col-md-4"><div class="card stat-card"><i class="fas fa-eye"></i><h3>{{ total_visits }}</h3><p>Site Visits</p></div></div>
        </div>
        <h3 class="mb-3">Recent Messages</h3>
        <div class="card"><div class="table-responsive"><table class="table"><thead><tr><th>Name</th><th>Email</th><th>Subject</th><th>Date</th><th>Status</th><th>Actions</th></tr></thead><tbody>{% for c in recent_contacts %}<tr><td>{{ c.name }}</td><td>{{ c.email }}</td><td>{{ c.subject or 'N/A' }}</td><td>{{ c.created_at[:10] }}</td><td><span class="badge {{ 'badge-read' if c.is_read else 'badge-unread' }}">{{ 'Read' if c.is_read else 'Unread' }}</span></td><td><a href="/admin/contacts/{{ c.id }}/read" class="btn btn-success btn-sm">Read</a> <a href="/admin/contacts/{{ c.id }}/delete" class="btn btn-danger btn-sm" onclick="return confirm('Delete?')">Del</a></td></tr>{% endfor %}</tbody></table></div></div>
        <a href="/admin/contacts" class="btn mt-3" style="background:linear-gradient(135deg,#FF6D00,#FF9100);color:white;padding:10px 30px;border-radius:50px;">View All Messages</a>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

ADMIN_CONTACTS_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>All Contacts</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body{background:#0A0E27;color:white;font-family:'Poppins',sans-serif}
        .navbar{background:rgba(10,14,39,0.95);border-bottom:1px solid rgba(255,109,0,0.3);padding:15px 0}
        .brand{background:linear-gradient(135deg,#FF9100,#FFD700);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:1.3rem;font-weight:800;text-decoration:none}
        .card{background:rgba(26,33,80,0.7);border:1px solid rgba(255,109,0,0.2);border-radius:20px;padding:25px}
        .table{color:white}.table th{border-color:rgba(255,255,255,0.1);color:#FFAB40}.table td{border-color:rgba(255,255,255,0.1)}
        .badge-read{background:#4ade80}.badge-unread{background:#FF6D00}
    </style>
</head>
<body>
    <nav class="navbar"><div class="container"><a href="/admin" class="brand"> Dashboard</a><a href="/admin/logout" class="btn btn-outline-danger btn-sm">Logout</a></div></nav>
    <div class="container py-5"><h2 class="mb-4">All Messages ({{ contacts|length }})</h2><div class="card"><div class="table-responsive"><table class="table"><thead><tr><th>#</th><th>Name</th><th>Email</th><th>Phone</th><th>Subject</th><th>Message</th><th>Date</th><th>Status</th><th>Actions</th></tr></thead><tbody>{% for c in contacts %}<tr><td>{{ c.id }}</td><td>{{ c.name }}</td><td>{{ c.email }}</td><td>{{ c.phone or '-' }}</td><td>{{ c.subject or '-' }}</td><td>{{ c.message[:40] }}...</td><td>{{ c.created_at[:10] }}</td><td><span class="badge {{ 'badge-read' if c.is_read else 'badge-unread' }}">{{ 'Read' if c.is_read else 'Unread' }}</span></td><td><a href="/admin/contacts/{{ c.id }}/read" class="btn btn-success btn-sm">Read</a> <a href="/admin/contacts/{{ c.id }}/delete" class="btn btn-danger btn-sm" onclick="return confirm('Delete?')">Del</a></td></tr>{% endfor %}</tbody></table></div></div></div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''


# ==================== ROUTES ====================

@app.route('/')
def home():
    return render_template_string(INDEX_TEMPLATE)

@app.route('/submit-contact', methods=['POST'])
def submit_contact():
    try:
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        errors = []
        if not name: errors.append('Name is required')
        if not email or '@' not in email: errors.append('Valid email is required')
        if not message: errors.append('Message is required')
        
        if errors:
            for error in errors: flash(error, 'error')
            return redirect(url_for('home', _anchor='contact'))
        
        conn = get_db()
        conn.execute('INSERT INTO contacts (name, email, phone, subject, message) VALUES (?, ?, ?, ?, ?)',
                    (name, email, phone, subject, message))
        conn.commit(); conn.close()
        
        flash(' Thank you! Your message has been sent successfully!', 'success')
        return redirect(url_for('home', _anchor='contact'))
    except Exception as e:
        flash(' Error occurred. Please try again.', 'error')
        return redirect(url_for('home', _anchor='contact'))

@app.route('/track-visit', methods=['POST'])
def track_visit():
    try:
        data = request.get_json()
        conn = get_db()
        conn.execute('INSERT INTO site_visits (ip_address, user_agent, page_visited) VALUES (?, ?, ?)',
                    (request.remote_addr, request.user_agent.string, data.get('page', 'home')))
        conn.commit(); conn.close()
        return jsonify({'status': 'success'})
    except: return jsonify({'status': 'error'})

# Admin Routes
def login_required(f):
    @wraps(f)
    def decorated(*a, **kw):
        if 'admin_logged_in' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('admin_login'))
        return f(*a, **kw)
    return decorated

@app.route('/admin')
@login_required
def admin_dashboard():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]
    unread = conn.execute('SELECT COUNT(*) FROM contacts WHERE is_read=0').fetchone()[0]
    visits = conn.execute('SELECT COUNT(*) FROM site_visits').fetchone()[0]
    recent = [dict(r) for r in conn.execute('SELECT * FROM contacts ORDER BY created_at DESC LIMIT 10').fetchall()]
    conn.close()
    return render_template_string(ADMIN_DASHBOARD_TEMPLATE, total_contacts=total, unread_contacts=unread, total_visits=visits, recent_contacts=recent)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        conn = get_db()
        user = conn.execute('SELECT * FROM admin_users WHERE username=?', (u,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], p):
            session['admin_logged_in'] = True; session['admin_username'] = u
            flash('Welcome Admin! ', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template_string(ADMIN_LOGIN_TEMPLATE)

@app.route('/admin/logout')
def admin_logout():
    session.clear(); flash('Logged out.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/contacts')
@login_required
def admin_contacts():
    conn = get_db()
    contacts = [dict(r) for r in conn.execute('SELECT * FROM contacts ORDER BY created_at DESC').fetchall()]
    conn.close()
    return render_template_string(ADMIN_CONTACTS_TEMPLATE, contacts=contacts)

@app.route('/admin/contacts/<int:cid>/read')
@login_required
def mark_read(cid):
    conn = get_db(); conn.execute('UPDATE contacts SET is_read=1 WHERE id=?', (cid,)); conn.commit(); conn.close()
    flash('Marked as read.', 'success')
    return redirect(url_for('admin_contacts'))

@app.route('/admin/contacts/<int:cid>/delete')
@login_required
def delete_contact(cid):
    conn = get_db(); conn.execute('DELETE FROM contacts WHERE id=?', (cid,)); conn.commit(); conn.close()
    flash('Deleted.', 'success')
    return redirect(url_for('admin_contacts'))

# Error Handlers
@app.errorhandler(404)
def e404(e):
    return '<html><body style="background:#0A0E27;color:white;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif"><div style="text-align:center"><h1 style="font-size:6rem;background:linear-gradient(135deg,#FF9100,#FFD700);-webkit-background-clip:text;-webkit-text-fill-color:transparent">404</h1><p>Page Not Found</p><a href="/" style="color:#FFAB40">Go Home</a></div></body></html>', 404

@app.errorhandler(500)
def e500(e):
    return '<html><body style="background:#0A0E27;color:white;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif"><div style="text-align:center"><h1 style="font-size:6rem;background:linear-gradient(135deg,#FF9100,#FFD700);-webkit-background-clip:text;-webkit-text-fill-color:transparent">500</h1><p>Server Error</p><a href="/" style="color:#FFAB40">Go Home</a></div></body></html>', 500

# ==================== MAIN ====================
if __name__ == '__main__':
    with app.app_context():
        init_db()
        insert_sample_data()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)