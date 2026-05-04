"""
Database module for the Expense Tracker application.
Handles all SQLite database operations.
"""

import sqlite3
import os
from datetime import datetime

class Database:
    def __init__(self, db_file="expenses.db"):
        """Initialize database connection and create tables if they don't exist."""
        self.db_file = db_file
        self.conn = None
        self.cursor = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Connect to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_file)
            self.conn.row_factory = sqlite3.Row  # This enables column access by name
            self.cursor = self.conn.cursor()
            print(f"Connected to database: {self.db_file}")
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
    
    def create_tables(self):
        """Create necessary tables if they don't exist."""
        try:
            # Create categories table
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
            ''')
            
            # Create expenses table
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY,
                amount REAL NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                category_id INTEGER,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            )
            ''')
            
            # Insert default categories if they don't exist
            default_categories = [
                "Food", "Transportation", "Housing", "Entertainment", 
                "Utilities", "Healthcare", "Education", "Shopping", "Other"
            ]
            
            for category in default_categories:
                self.cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (category,))
            
            self.conn.commit()
            print("Database tables created successfully")
        except sqlite3.Error as e:
            print(f"Error creating tables: {e}")
    
    def add_expense(self, amount, description, date, category):
        """Add a new expense to the database."""
        try:
            # Get category_id
            self.cursor.execute("SELECT id FROM categories WHERE name = ?", (category,))
            result = self.cursor.fetchone()
            
            if result:
                category_id = result[0]
            else:
                # Create new category if it doesn't exist
                self.cursor.execute("INSERT INTO categories (name) VALUES (?)", (category,))
                category_id = self.cursor.lastrowid
            
            # Insert expense
            self.cursor.execute(
                "INSERT INTO expenses (amount, description, date, category_id) VALUES (?, ?, ?, ?)",
                (amount, description, date, category_id)
            )
            
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error adding expense: {e}")
            return False
    
    def get_all_expenses(self):
        """Get all expenses with category names."""
        try:
            self.cursor.execute('''
            SELECT e.id, e.amount, e.description, e.date, c.name as category
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            ORDER BY e.date DESC
            ''')
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error retrieving expenses: {e}")
            return []
    
    def get_expenses_by_category(self):
        """Get total expenses grouped by category."""
        try:
            self.cursor.execute('''
            SELECT c.name as category, SUM(e.amount) as total
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            GROUP BY c.name
            ORDER BY total DESC
            ''')
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error retrieving category expenses: {e}")
            return []
    
    def get_expenses_by_date_range(self, start_date, end_date):
        """Get expenses within a date range."""
        try:
            self.cursor.execute('''
            SELECT e.id, e.amount, e.description, e.date, c.name as category
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.date BETWEEN ? AND ?
            ORDER BY e.date DESC
            ''', (start_date, end_date))
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error retrieving expenses by date range: {e}")
            return []
    
    def get_total_expenses(self):
        """Get the total sum of all expenses."""
        try:
            self.cursor.execute("SELECT SUM(amount) as total FROM expenses")
            result = self.cursor.fetchone()
            return result['total'] if result['total'] else 0
        except sqlite3.Error as e:
            print(f"Error retrieving total expenses: {e}")
            return 0
    
    def get_all_categories(self):
        """Get all expense categories."""
        try:
            self.cursor.execute("SELECT name FROM categories ORDER BY name")
            categories = [row['name'] for row in self.cursor.fetchall()]
            return categories
        except sqlite3.Error as e:
            print(f"Error retrieving categories: {e}")
            return []
    
    def delete_expense(self, expense_id):
        """Delete an expense by ID."""
        try:
            self.cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error deleting expense: {e}")
            return False
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            print("Database connection closed")