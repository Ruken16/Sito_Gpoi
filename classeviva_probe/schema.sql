-- Schema MySQL per il progetto ClasseViva Tutor

CREATE DATABASE IF NOT EXISTS cv_tutor;
USE cv_tutor;

-- Tabella Utenti Principale
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    school_level ENUM('Medie', 'Superiori', 'Università') NOT NULL,
    cv_username VARCHAR(255), -- Username ClasseViva (opzionale fino al login CV)
    cv_password VARCHAR(255), -- Password ClasseViva (criptata o token se possibile)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Tabella Profili (Preferenze di studio)
CREATE TABLE IF NOT EXISTS profiles (
    user_id INT PRIMARY KEY,
    display_name VARCHAR(255) NOT NULL,
    study_goal TEXT NOT NULL,
    learning_mode ENUM('standard', 'intensiva', 'dsa') DEFAULT 'standard',
    daily_study_minutes INT NOT NULL DEFAULT 120,
    session_minutes INT NOT NULL DEFAULT 40,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tabella Attività / Compiti
CREATE TABLE IF NOT EXISTS tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    due_date DATE NOT NULL,
    category VARCHAR(50) NOT NULL, -- compito, verifica, ripasso
    estimated_minutes INT NOT NULL,
    difficulty INT NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
    priority INT NOT NULL CHECK (priority BETWEEN 1 AND 5),
    status ENUM('todo', 'doing', 'done') DEFAULT 'todo',
    notes TEXT,
    source VARCHAR(50) DEFAULT 'manual', -- manual o classeviva
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tabella Chat Threads
CREATE TABLE IF NOT EXISTS chat_threads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tabella Messaggi Chat
CREATE TABLE IF NOT EXISTS chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    thread_id INT NOT NULL,
    user_id INT NOT NULL,
    role ENUM('user', 'assistant') NOT NULL,
    content TEXT NOT NULL,
    context_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
