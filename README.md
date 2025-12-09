# FastAPI Calculation App

A robust, full-stack web application built with **FastAPI**, **SQLAlchemy**, and **PostgreSQL**. This project implements a secure calculation engine with BREAD operations, user profile management, and a modern frontend interface.

## 🚀 Features

### Core Functionality (BREAD)
- **Browse:** View calculation history with dynamic tables.
- **Read:** Inspect specific calculation details.
- **Edit:** Update calculation inputs with automatic result re-computation.
- **Add:** Perform new mathematical operations (Add, Subtract, Multiply, Divide).
- **Delete:** Remove unwanted records.

### ✨ New Feature: User Profile Management
- **Profile Updates:** Users can update their First Name, Last Name, and Email.
- **Security:** Secure password change functionality with automatic hashing.
- **Validation:** Prevents duplicate usernames/emails during updates.

### 🛡️ Security & DevOps
- **Authentication:** JWT (JSON Web Tokens) for stateless session management.
- **Containerization:** Fully Dockerized (Web App + PostgreSQL + pgAdmin).
- **CI/CD:** GitHub Actions pipeline for automated testing and Trivy vulnerability scanning.
- **Quality:** 100% Test Coverage for critical paths using Pytest and Playwright.

---

## 🛠️ Setup & Installation

### Prerequisites
- Docker Desktop installed and running.

### Running the App
1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd <your-repo-folder>