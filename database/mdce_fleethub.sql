DROP DATABASE IF EXISTS mdce_fleethub;
CREATE DATABASE mdce_fleethub;
USE mdce_fleethub;

CREATE TABLE admin (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(100) NOT NULL UNIQUE,
  password VARCHAR(255) NOT NULL,
  full_name VARCHAR(100) NOT NULL,
  position VARCHAR(50),
  contact_no VARCHAR(20)
) ENGINE=InnoDB;

CREATE TABLE jeeps (
  id INT AUTO_INCREMENT PRIMARY KEY,
  jeep_no VARCHAR(10) NOT NULL UNIQUE,
  plate_no VARCHAR(20) NOT NULL UNIQUE,
  route VARCHAR(100),
  registration_expiry DATE,
  driver_assigned_since DATE
) ENGINE=InnoDB;

CREATE TABLE drivers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(100) NOT NULL,
  photo_path VARCHAR(255),
  birth_date DATE,
  address VARCHAR(255),
  contact_no VARCHAR(20),
  license_no VARCHAR(30),
  license_expiry DATE,
  jeep_id INT UNIQUE,
  date_joined DATE,
  emergency_name VARCHAR(100),
  emergency_contact_no VARCHAR(20),
  FOREIGN KEY (jeep_id) REFERENCES jeeps(id)
) ENGINE=InnoDB;

CREATE TABLE documents (
  id INT AUTO_INCREMENT PRIMARY KEY,
  jeep_id INT NULL,
  driver_id INT NULL,
  doc_type VARCHAR(50) NOT NULL,
  doc_date DATE,
  expiry_date DATE NULL,
  file_path VARCHAR(255) NOT NULL,
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (jeep_id) REFERENCES jeeps(id),
  FOREIGN KEY (driver_id) REFERENCES drivers(id)
) ENGINE=InnoDB;

CREATE TABLE issues (
  id INT AUTO_INCREMENT PRIMARY KEY,
  jeep_id INT NOT NULL,
  driver_id INT NULL,
  issue_type VARCHAR(30),
  issue TEXT NOT NULL,
  status ENUM('Open','In Progress','Resolved') DEFAULT 'Open',
  date_broken DATE NOT NULL,
  date_fixed DATE NULL,
  cost DECIMAL(10,2) NULL,
  shop_place VARCHAR(100),
  technician VARCHAR(100),
  paid_by ENUM('Company','Driver') NULL,
  repair_details VARCHAR(255),
  substitute_jeep_id INT NULL,
  FOREIGN KEY (jeep_id) REFERENCES jeeps(id),
  FOREIGN KEY (driver_id) REFERENCES drivers(id),
  FOREIGN KEY (substitute_jeep_id) REFERENCES jeeps(id)
) ENGINE=InnoDB;

CREATE TABLE issue_photos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  issue_id INT NOT NULL,
  file_path VARCHAR(255) NOT NULL,
  FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO admin (email, password, full_name, position, contact_no)
VALUES ('admin@mdce.com', 'admin123', 'Test Admin', 'Admin', '09000000000');