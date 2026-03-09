-- ============================================
-- Database: problem_reporting_system
-- WAMP Server Compatible (Old MySQL)
-- Charset: utf8 (NOT utf8mb4)
-- ============================================

CREATE DATABASE IF NOT EXISTS problem_reporting_system
  CHARACTER SET utf8
  COLLATE utf8_general_ci;

USE problem_reporting_system;

-- ============================================
-- TABLE: users
-- ============================================
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  username VARCHAR(100) NOT NULL UNIQUE,
  mobile VARCHAR(20) DEFAULT NULL,
  address VARCHAR(255) DEFAULT NULL,
  password VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8;


-- ============================================
-- TABLE: departments
-- ============================================
CREATE TABLE IF NOT EXISTS departments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  department_name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;


-- ============================================
-- TABLE: officers
-- department_id stored as VARCHAR because your code stores department name
-- ============================================
CREATE TABLE IF NOT EXISTS officers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  username VARCHAR(100) NOT NULL UNIQUE,
  department_id VARCHAR(100) NOT NULL,
  mobile VARCHAR(20) DEFAULT NULL,
  address VARCHAR(255) DEFAULT NULL,
  password VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8;


-- ============================================
-- TABLE: admin
-- ============================================
CREATE TABLE IF NOT EXISTS admin (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL UNIQUE,
  password VARCHAR(150) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Default Admin Login
INSERT INTO admin (username, password)
VALUES ('admin', 'admin123');


-- ============================================
-- TABLE: problems
-- department stored as VARCHAR (department name)
-- assigned_officer_id links to officers.id
-- ============================================
CREATE TABLE IF NOT EXISTS problems (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  department VARCHAR(100) NOT NULL,
  description TEXT NOT NULL,
  priority VARCHAR(50) DEFAULT 'Normal',
  image_path VARCHAR(255) DEFAULT NULL,
  location VARCHAR(100) DEFAULT NULL,
  status VARCHAR(50) DEFAULT 'Pending',
  latitude VARCHAR(50) DEFAULT NULL,
  longitude VARCHAR(50) DEFAULT NULL,
  assigned_officer_id INT DEFAULT NULL,
  proof_image VARCHAR(255) DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (assigned_officer_id) REFERENCES officers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;


-- ============================================
-- TABLE: review_complaints
-- ============================================
CREATE TABLE IF NOT EXISTS review_complaints (
  id INT AUTO_INCREMENT PRIMARY KEY,
  problem_id INT NOT NULL,
  user_id INT NOT NULL,
  message TEXT NOT NULL,
  reply_message TEXT DEFAULT NULL,
  status VARCHAR(50) DEFAULT 'Pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  reply_at DATETIME DEFAULT NULL,

  FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;


-- ============================================
-- Sample Departments (Optional)
-- ============================================
INSERT INTO departments (department_name) VALUES
('Road Maintenance'),
('Water Supply'),
('Electricity'),
('Public Safety'),
('Health Department');
