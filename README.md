# 🎬 Cinema Online Booking System

*A full-stack cinema ticket booking platform built with Django REST Framework & React.js.*

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.11-blue.svg)
![Django](https://img.shields.io/badge/Django-5.x-green.svg)
![React](https://img.shields.io/badge/React-18-blue.svg)
![MySQL](https://img.shields.io/badge/MySQL-8-orange.svg)
![Stripe](https://img.shields.io/badge/Stripe-Payments-purple.svg)

---

## 📌 Overview

Cinema Online Booking System is a complete ticket reservation platform where users can browse movies, view details, choose showtimes, book seats, make secure payments (Stripe), and download QR-coded tickets.

The project includes full **authentication**, **movie management**, **booking logic**, **Stripe integration**, **PDF ticket generation**, and a modern **React frontend**.

---

## 🚀 Features

### 🎥 Movies & Content

* View all movies (poster, rating, trailer, genre, actors)
* Movie detail page with full information
* Real dataset of 10K+ movies (TMDB based)

### 👤 User System

* JWT-based login & register
* Protected endpoints
* User profile page with previous bookings

### 🪑 Booking System

* Select showtime
* Add seats & tickets
* Book & pay through Stripe
* Automatic booking confirmation

### 💳 Payment Flow

* Stripe Checkout Session
* Stripe Webhooks to verify payment
* Ticket creation on successful payment

### 🎫 Ticket System

* Auto-generated PDF ticket
* QR verification code
* Movie poster embedded
* Downloadable from frontend

### 🤖 AI Chatbot (Optional)

* Powered by Rasa
* DVD server + Django integration

---

## 🏗️ System Architecture

```
Frontend (React + Vite)
        |
        | fetch()
        v
Backend API (Django REST)
        |
        | DB ORM
        v
     MySQL DB
        |
        | Celery
        v
Async Workers (Ticket PDF)
        |
        | Payment Status
        v
Stripe Payment Gateway
```

---

## 📂 Project Structure

### **Backend (Django)**

```
/backend
 ├── users/
 ├── movies/
 ├── showtimes/
 ├── booking/
 ├── chatbot/
 ├── tickets/
 ├── cinema_backend/
 ├── media/
 └── requirements.txt
```

### **Frontend (React)**

```
/frontend
 ├── src/
 │   ├── api/
 │   ├── components/
 │   ├── context/
 │   ├── pages/
 │   ├── assets/
 │   └── App.jsx
 └── package.json
```

---

## 🛠️ Tech Stack

### **Backend**

* Python 3.11
* Django 5.x
* Django REST Framework
* MySQL
* Celery + Redis
* Stripe API
* Pillow
* qrcode
* drf-yasg (Swagger)

### **Frontend**

* React 18
* Vite
* TailwindCSS
* JWT Auth
* Axios

---

## ⚙️ Installation

### 🔹 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/cinema-online-system.git
cd cinema-online-system
```

---

## 🛠 Backend Setup (Django)

### 🔹 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Mac / Linux
venv\Scripts\activate     # Windows
```

### 🔹 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 🔹 4. Apply migrations

```bash
python manage.py migrate
```

### 🔹 5. Run the server

```bash
python manage.py runserver
```

---

## 🖥 Frontend Setup (React)

### 🔹 1. Install deps

```bash
cd frontend
npm install
```

### 🔹 2. Run frontend

```bash
npm run dev
```

---

## 🔐 Environment Variables

### Backend `.env`

```
SECRET_KEY=your_secret
DEBUG=True
DB_NAME=cinema_db
DB_USER=root
DB_PASSWORD=password
DB_HOST=127.0.0.1
DB_PORT=3306

STRIPE_SECRET_KEY=your_key
STRIPE_PUBLIC_KEY=your_key
TMDB_KEY=your_key
```

### Frontend `.env`

```
VITE_API_URL=http://127.0.0.1:8000/api/
```

---

## 🧪 API Documentation

Swagger UI:

```
http://127.0.0.1:8000/swagger/
```

---

## 📡 Main API Endpoints

### **Movies**

```
GET /api/movies/
GET /api/movies/<id>/
```

### **Auth**

```
POST /api/users/register/
POST /api/users/login/
GET  /api/users/profile/
```

### **Booking**

```
POST /api/bookings/create/
GET  /api/bookings/user/
```

### **Payment**

```
POST /api/stripe/create-checkout-session/
POST /api/stripe/webhook/
```

### **Tickets**

```
GET /api/tickets/download/<ticket_id>/
```

---


## 🧩 Future Enhancements

* Seat selection UI (graphical grid)
* Movie recommendations system (ML based)
* Admin dashboard for managing movies & showtimes
* Push notifications for showtime reminders
* Multi-language support

---

## 📜 License

This project is **MIT Licensed**.
