"""
Modern Personal Expense Tracker
A simple GUI application to track personal expenses using CustomTkinter and SQLite.
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib
import csv
matplotlib.use("TkAgg")

# Import our database module
from database import Database

# Set appearance mode and default color theme
ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class ExpenseTrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Initialize database
        self.db = Database()
        
        # Configure window
        self.title("Modern Personal Expense Tracker")
        self.geometry("1000x650")
        self.minsize(800, 600)
        
        # Create fonts
        self.title_font = ctk.CTkFont(family="Arial", size=24, weight="bold")
        self.header_font = ctk.CTkFont(family="Arial", size=18, weight="bold")
        self.normal_font = ctk.CTkFont(family="Arial", size=14)
        
        # Create main frame
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create sidebar frame
        self.sidebar_frame = ctk.CTkFrame(self.main_frame, width=200)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10), pady=0)
        
        # Create content frame
        self.content_frame = ctk.CTkFrame(self.main_frame)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Setup sidebar
        self.setup_sidebar()
        
        # Setup dashboard (default view)
        self.current_frame = None
        self.show_dashboard()
    
    def setup_sidebar(self):
        """Setup the sidebar with navigation buttons."""
        # App title
        title_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Expense Tracker", 
            font=self.title_font
        )
        title_label.pack(pady=(20, 30), padx=20)
        
        # Navigation buttons
        self.dashboard_btn = ctk.CTkButton(
            self.sidebar_frame,
            text="Dashboard",
            font=self.normal_font,
            height=40,
            command=self.show_dashboard
        )
        self.dashboard_btn.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.add_expense_btn = ctk.CTkButton(
            self.sidebar_frame,
            text="Add Expense",
            font=self.normal_font,
            height=40,
            command=self.show_add_expense
        )
        self.add_expense_btn.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.view_expenses_btn = ctk.CTkButton(
            self.sidebar_frame,
            text="View Expenses",
            font=self.normal_font,
            height=40,
            command=self.show_view_expenses
        )
        self.view_expenses_btn.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.reports_btn = ctk.CTkButton(
            self.sidebar_frame,
            text="Reports",
            font=self.normal_font,
            height=40,
            command=self.show_reports
        )
        self.reports_btn.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        # Appearance mode selector
        appearance_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Appearance Mode:", 
            font=self.normal_font
        )
        appearance_label.pack(pady=(30, 0), padx=20)
        
        appearance_option = ctk.CTkOptionMenu(
            self.sidebar_frame,
            values=["System", "Dark", "Light"],
            command=self.change_appearance_mode
        )
        appearance_option.pack(pady=(10, 20), padx=20)
        appearance_option.set("System")
    
    def change_appearance_mode(self, new_appearance_mode):
        """Change the app's appearance mode."""
        ctk.set_appearance_mode(new_appearance_mode)
    
    def clear_content_frame(self):
        """Clear all widgets from the content frame."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
    def show_dashboard(self):
        """Show the dashboard view."""
        self.clear_content_frame()
        
        # Dashboard title
        title_label = ctk.CTkLabel(
            self.content_frame, 
            text="Dashboard", 
            font=self.title_font
        )
        title_label.pack(pady=(20, 20), padx=20, anchor="w")
        
        # Create summary cards frame
        summary_frame = ctk.CTkFrame(self.content_frame)
        summary_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        # Total expenses card
        total_card = ctk.CTkFrame(summary_frame)
        total_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10), pady=10)
        
        total_label = ctk.CTkLabel(
            total_card, 
            text="Total Expenses", 
            font=self.header_font
        )
        total_label.pack(pady=(15, 5), padx=20)
        
        total_amount = self.db.get_total_expenses()
        total_amount_label = ctk.CTkLabel(
            total_card, 
            text=f"₹ {total_amount:.2f}", 
            font=self.title_font
        )
        total_amount_label.pack(pady=(5, 15), padx=20)
        
        # Create charts frame
        charts_frame = ctk.CTkFrame(self.content_frame)
        charts_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # Category distribution chart
        category_expenses = self.db.get_expenses_by_category()
        
        if category_expenses:
            # Create matplotlib figure
            fig, ax = plt.subplots(figsize=(8, 4), dpi=100)
            fig.patch.set_facecolor('none')  # Transparent background
            
            categories = [item['category'] for item in category_expenses]
            amounts = [item['total'] for item in category_expenses]
            
            # Create pie chart
            wedges, texts, autotexts = ax.pie(
                amounts, 
                labels=None,
                autopct='%1.1f%%',
                startangle=90,
                wedgeprops={'width': 0.5, 'edgecolor': 'white'}
            )
            
            # Equal aspect ratio ensures that pie is drawn as a circle
            ax.axis('equal')
            ax.set_title('Expenses by Category', color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            # Set text colors based on appearance mode
            plt.setp(autotexts, color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            # Add legend
            ax.legend(
                wedges, 
                categories,
                title="Categories",
                loc="center left",
                bbox_to_anchor=(1, 0, 0.5, 1)
            )
            
            # Create canvas
            canvas = FigureCanvasTkAgg(fig, master=charts_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            no_data_label = ctk.CTkLabel(
                charts_frame, 
                text="No expense data available. Add some expenses to see charts.", 
                font=self.normal_font
            )
            no_data_label.pack(pady=50)
    
    def show_add_expense(self):
        """Show the add expense view."""
        self.clear_content_frame()
        
        # Add expense title
        title_label = ctk.CTkLabel(
            self.content_frame, 
            text="Add New Expense", 
            font=self.title_font
        )
        title_label.pack(pady=(20, 30), padx=20, anchor="w")
        
        # Create form frame
        form_frame = ctk.CTkFrame(self.content_frame)
        form_frame.pack(fill=tk.BOTH, padx=20, pady=(0, 20), expand=True)
        
        # Create form with grid layout
        # Amount
        amount_label = ctk.CTkLabel(
            form_frame, 
            text="Amount (₹):", 
            font=self.normal_font
        )
        amount_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        amount_entry = ctk.CTkEntry(
            form_frame,
            font=self.normal_font,
            width=200
        )
        amount_entry.grid(row=0, column=1, padx=20, pady=(20, 10), sticky="w")
        
        # Description
        desc_label = ctk.CTkLabel(
            form_frame, 
            text="Description:", 
            font=self.normal_font
        )
        desc_label.grid(row=1, column=0, padx=20, pady=10, sticky="w")
        
        desc_entry = ctk.CTkEntry(
            form_frame,
            font=self.normal_font,
            width=300
        )
        desc_entry.grid(row=1, column=1, padx=20, pady=10, sticky="w")
        
        # Date
        date_label = ctk.CTkLabel(
            form_frame, 
            text="Date:", 
            font=self.normal_font
        )
        date_label.grid(row=2, column=0, padx=20, pady=10, sticky="w")
        
        # Date frame with individual components
        date_frame = ctk.CTkFrame(form_frame)
        date_frame.grid(row=2, column=1, padx=20, pady=10, sticky="w")
        
        # Get current date
        today = datetime.now()
        
        # Day dropdown
        day_var = tk.StringVar(value=str(today.day))
        day_dropdown = ctk.CTkOptionMenu(
            date_frame,
            values=[str(i).zfill(2) for i in range(1, 32)],
            variable=day_var,
            width=60
        )
        day_dropdown.pack(side=tk.LEFT, padx=(0, 5))
        
        # Month dropdown
        months = ["01", "02", "03", "04", "05", "06", 
                  "07", "08", "09", "10", "11", "12"]
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        month_var = tk.StringVar(value=str(today.month).zfill(2))
        month_dropdown = ctk.CTkOptionMenu(
            date_frame,
            values=months,
            variable=month_var,
            width=60
        )
        month_dropdown.pack(side=tk.LEFT, padx=5)
        
        # Year dropdown
        current_year = today.year
        years = [str(year) for year in range(current_year-5, current_year+1)]
        
        year_var = tk.StringVar(value=str(current_year))
        year_dropdown = ctk.CTkOptionMenu(
            date_frame,
            values=years,
            variable=year_var,
            width=80
        )
        year_dropdown.pack(side=tk.LEFT, padx=(5, 0))
        
        # Category
        category_label = ctk.CTkLabel(
            form_frame, 
            text="Category:", 
            font=self.normal_font
        )
        category_label.grid(row=3, column=0, padx=20, pady=10, sticky="w")
        
        # Get categories from database
        categories = self.db.get_all_categories()
        
        category_var = tk.StringVar(value=categories[0] if categories else "Other")
        category_dropdown = ctk.CTkOptionMenu(
            form_frame,
            values=categories,
            variable=category_var,
            width=200
        )
        category_dropdown.grid(row=3, column=1, padx=20, pady=10, sticky="w")
        
        # Add custom category option
        def add_custom_category():
            dialog = ctk.CTkInputDialog(
                text="Enter new category name:", 
                title="Add Custom Category"
            )
            new_category = dialog.get_input()
            
            if new_category and new_category.strip():
                new_category = new_category.strip()
                # Add to database if it doesn't exist
                if new_category not in categories:
                    categories.append(new_category)
                    category_dropdown.configure(values=categories)
                    category_var.set(new_category)
        
        add_category_btn = ctk.CTkButton(
            form_frame,
            text="+ Add Custom",
            font=self.normal_font,
            width=120,
            command=add_custom_category
        )
        add_category_btn.grid(row=3, column=2, padx=20, pady=10, sticky="w")
        
        # Submit button
        def save_expense():
            # Validate amount
            try:
                amount = float(amount_entry.get())
                if amount <= 0:
                    messagebox.showerror("Invalid Amount", "Please enter a positive amount.")
                    return
            except ValueError:
                messagebox.showerror("Invalid Amount", "Please enter a valid number for amount.")
                return
            
            # Get description
            description = desc_entry.get().strip()
            
            # Format date
            date_str = f"{year_var.get()}-{month_var.get()}-{day_var.get()}"
            
            # Get category
            category = category_var.get()
            
            # Save to database
            success = self.db.add_expense(amount, description, date_str, category)
            
            if success:
                messagebox.showinfo("Success", "Expense added successfully!")
                # Clear form
                amount_entry.delete(0, tk.END)
                desc_entry.delete(0, tk.END)
                # Reset date to today
                day_var.set(str(today.day).zfill(2))
                month_var.set(str(today.month).zfill(2))
                year_var.set(str(today.year))
                # Reset category
                category_var.set(categories[0] if categories else "Other")
                # Refresh dashboard
                self.show_dashboard()
            else:
                messagebox.showerror("Error", "Failed to add expense. Please try again.")
        
        submit_btn = ctk.CTkButton(
            form_frame,
            text="Save Expense",
            font=self.normal_font,
            height=40,
            command=save_expense
        )
        submit_btn.grid(row=4, column=0, columnspan=3, padx=20, pady=(30, 20), sticky="ew")
    
    def show_view_expenses(self):
        """Show the view expenses screen."""
        self.clear_content_frame()
        
        # View expenses title
        title_label = ctk.CTkLabel(
            self.content_frame, 
            text="View Expenses", 
            font=self.title_font
        )
        title_label.pack(pady=(20, 10), padx=20, anchor="w")
        
        # Create filter frame
        filter_frame = ctk.CTkFrame(self.content_frame)
        filter_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        # Filter label
        filter_label = ctk.CTkLabel(
            filter_frame, 
            text="Filter by:", 
            font=self.normal_font
        )
        filter_label.pack(side=tk.LEFT, padx=(20, 10), pady=10)
        
        # Date range options
        date_options = ["All Time", "This Month", "Last Month", "Last 3 Months", "This Year"]
        date_var = tk.StringVar(value=date_options[0])
        
        date_dropdown = ctk.CTkOptionMenu(
            filter_frame,
            values=date_options,
            variable=date_var,
            width=150,
            command=self.filter_expenses
        )
        date_dropdown.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Category filter
        category_label = ctk.CTkLabel(
            filter_frame, 
            text="Category:", 
            font=self.normal_font
        )
        category_label.pack(side=tk.LEFT, padx=(20, 10), pady=10)
        
        # Get categories from database
        categories = ["All Categories"] + self.db.get_all_categories()
        
        category_var = tk.StringVar(value=categories[0])
        category_dropdown = ctk.CTkOptionMenu(
            filter_frame,
            values=categories,
            variable=category_var,
            width=150,
            command=self.filter_expenses
        )
        category_dropdown.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Create expenses list frame
        expenses_frame = ctk.CTkScrollableFrame(self.content_frame)
        expenses_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # Store references to widgets and variables
        self.expenses_frame = expenses_frame
        self.date_var = date_var
        self.category_var = category_var
        
        # Load expenses
        self.filter_expenses()
    
    def filter_expenses(self, *args):
        """Filter expenses based on selected criteria."""
        # Clear expenses frame
        for widget in self.expenses_frame.winfo_children():
            widget.destroy()
        
        # Get filter values
        date_filter = self.date_var.get()
        category_filter = self.category_var.get()
        
        # Calculate date range
        today = datetime.now()
        start_date = None
        end_date = today.strftime("%Y-%m-%d")
        
        if date_filter == "This Month":
            start_date = datetime(today.year, today.month, 1).strftime("%Y-%m-%d")
        elif date_filter == "Last Month":
            last_month = today.month - 1 if today.month > 1 else 12
            last_month_year = today.year if today.month > 1 else today.year - 1
            start_date = datetime(last_month_year, last_month, 1).strftime("%Y-%m-%d")
            
            # Calculate end of last month
            if today.month > 1:
                end_date = datetime(today.year, today.month, 1) - timedelta(days=1)
            else:
                end_date = datetime(today.year - 1, 12, 31)
            end_date = end_date.strftime("%Y-%m-%d")
        elif date_filter == "Last 3 Months":
            three_months_ago = today.month - 3
            year_offset = 0
            while three_months_ago <= 0:
                three_months_ago += 12
                year_offset -= 1
            start_date = datetime(today.year + year_offset, three_months_ago, 1).strftime("%Y-%m-%d")
        elif date_filter == "This Year":
            start_date = datetime(today.year, 1, 1).strftime("%Y-%m-%d")
        else:  # All Time
            start_date = "1900-01-01"  # A date far in the past
        
        # Get expenses from database
        if date_filter == "All Time" and category_filter == "All Categories":
            expenses = self.db.get_all_expenses()
        else:
            expenses = self.db.get_expenses_by_date_range(start_date, end_date)
            
            # Filter by category if needed
            if category_filter != "All Categories":
                expenses = [e for e in expenses if e['category'] == category_filter]
        
        # Display expenses
        if expenses:
            # Create header
            header_frame = ctk.CTkFrame(self.expenses_frame, fg_color="transparent")
            header_frame.pack(fill=tk.X, padx=5, pady=(5, 10))
            
            date_header = ctk.CTkLabel(
                header_frame, 
                text="Date", 
                font=self.header_font,
                width=100
            )
            date_header.pack(side=tk.LEFT, padx=(5, 10))
            
            desc_header = ctk.CTkLabel(
                header_frame, 
                text="Description", 
                font=self.header_font,
                width=200
            )
            desc_header.pack(side=tk.LEFT, padx=10)
            
            category_header = ctk.CTkLabel(
                header_frame, 
                text="Category", 
                font=self.header_font,
                width=150
            )
            category_header.pack(side=tk.LEFT, padx=10)
            
            amount_header = ctk.CTkLabel(
                header_frame, 
                text="Amount", 
                font=self.header_font,
                width=100
            )
            amount_header.pack(side=tk.LEFT, padx=10)
            
            # Add separator
            separator = ctk.CTkFrame(self.expenses_frame, height=2)
            separator.pack(fill=tk.X, padx=5, pady=(0, 10))
            
            # Display each expense
            for expense in expenses:
                expense_frame = ctk.CTkFrame(self.expenses_frame, fg_color="transparent")
                expense_frame.pack(fill=tk.X, padx=5, pady=(0, 10))
                
                # Format date (from YYYY-MM-DD to DD-MM-YYYY)
                date_parts = expense['date'].split('-')
                formatted_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
                
                date_label = ctk.CTkLabel(
                    expense_frame, 
                    text=formatted_date, 
                    font=self.normal_font,
                    width=100
                )
                date_label.pack(side=tk.LEFT, padx=(5, 10))
                
                desc_text = expense['description'] if expense['description'] else "N/A"
                desc_label = ctk.CTkLabel(
                    expense_frame, 
                    text=desc_text, 
                    font=self.normal_font,
                    width=200
                )
                desc_label.pack(side=tk.LEFT, padx=10)
                
                category_label = ctk.CTkLabel(
                    expense_frame, 
                    text=expense['category'], 
                    font=self.normal_font,
                    width=150
                )
                category_label.pack(side=tk.LEFT, padx=10)
                
                amount_label = ctk.CTkLabel(
                    expense_frame, 
                    text=f"₹ {expense['amount']:.2f}", 
                    font=self.normal_font,
                    width=100
                )
                amount_label.pack(side=tk.LEFT, padx=10)
                
                # Delete button
                def create_delete_callback(expense_id):
                    def delete_callback():
                        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this expense?"):
                            success = self.db.delete_expense(expense_id)
                            if success:
                                messagebox.showinfo("Success", "Expense deleted successfully!")
                                self.filter_expenses()  # Refresh the list
                                self.show_dashboard()  # Update dashboard
                            else:
                                messagebox.showerror("Error", "Failed to delete expense.")
                    return delete_callback
                
                delete_btn = ctk.CTkButton(
                    expense_frame,
                    text="Delete",
                    font=self.normal_font,
                    width=80,
                    fg_color="#FF5555",
                    hover_color="#FF0000",
                    command=create_delete_callback(expense['id'])
                )
                delete_btn.pack(side=tk.RIGHT, padx=10)
        else:
            no_data_label = ctk.CTkLabel(
                self.expenses_frame, 
                text="No expenses found for the selected filters.", 
                font=self.normal_font
            )
            no_data_label.pack(pady=50)
    
    def show_reports(self):
        """Show the reports and analytics view."""
        self.clear_content_frame()
        
        # Reports title
        title_label = ctk.CTkLabel(
            self.content_frame, 
            text="Reports & Analytics", 
            font=self.title_font
        )
        title_label.pack(pady=(20, 20), padx=20, anchor="w")
        
        # Create tabs
        tabview = ctk.CTkTabview(self.content_frame)
        tabview.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # Add tabs
        tabview.add("Category Analysis")
        tabview.add("Monthly Trends")
        tabview.add("Export Data")
        
        # Set default tab
        tabview.set("Category Analysis")
        
        # Category Analysis Tab
        category_frame = tabview.tab("Category Analysis")
        
        # Get category data
        category_expenses = self.db.get_expenses_by_category()
        
        if category_expenses:
            # Create matplotlib figure for pie chart
            fig1, ax1 = plt.subplots(figsize=(8, 5), dpi=100)
            fig1.patch.set_facecolor('none')  # Transparent background
            
            categories = [item['category'] for item in category_expenses]
            amounts = [item['total'] for item in category_expenses]
            
            # Create pie chart
            wedges, texts, autotexts = ax1.pie(
                amounts, 
                labels=None,
                autopct='%1.1f%%',
                startangle=90,
                wedgeprops={'width': 0.5, 'edgecolor': 'white'}
            )
            
            # Equal aspect ratio ensures that pie is drawn as a circle
            ax1.axis('equal')
            ax1.set_title('Expenses by Category', color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            # Set text colors based on appearance mode
            plt.setp(autotexts, color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            # Add legend
            ax1.legend(
                wedges, 
                categories,
                title="Categories",
                loc="center left",
                bbox_to_anchor=(1, 0, 0.5, 1)
            )
            
            # Create canvas
            canvas1 = FigureCanvasTkAgg(fig1, master=category_frame)
            canvas1.draw()
            canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=10)
            
            # Create bar chart for category comparison
            fig2, ax2 = plt.subplots(figsize=(8, 4), dpi=100)
            fig2.patch.set_facecolor('none')  # Transparent background
            
            # Create horizontal bar chart
            bars = ax2.barh(categories, amounts, color='royalblue')
            
            # Add labels
            for bar in bars:
                width = bar.get_width()
                label_x_pos = width + 0.5
                ax2.text(label_x_pos, bar.get_y() + bar.get_height()/2, f'₹{width:.2f}',
                        va='center', color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            ax2.set_title('Category Comparison', color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            ax2.set_xlabel('Amount (₹)', color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            ax2.set_ylabel('Category', color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            # Set tick colors based on appearance mode
            ax2.tick_params(colors='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            # Adjust layout
            plt.tight_layout()
            
            # Create canvas
            canvas2 = FigureCanvasTkAgg(fig2, master=category_frame)
            canvas2.draw()
            canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=10)
        else:
            no_data_label = ctk.CTkLabel(
                category_frame, 
                text="No expense data available. Add some expenses to see analytics.", 
                font=self.normal_font
            )
            no_data_label.pack(pady=50)
        
        # Monthly Trends Tab
        monthly_frame = tabview.tab("Monthly Trends")
        
        # Get all expenses
        all_expenses = self.db.get_all_expenses()
        
        if all_expenses:
            # Process data for monthly trends
            monthly_data = {}
            
            for expense in all_expenses:
                # Extract year and month from date
                date_parts = expense['date'].split('-')
                year_month = f"{date_parts[0]}-{date_parts[1]}"
                
                # Add to monthly data
                if year_month in monthly_data:
                    monthly_data[year_month] += expense['amount']
                else:
                    monthly_data[year_month] = expense['amount']
            
            # Sort by date
            sorted_months = sorted(monthly_data.keys())
            monthly_amounts = [monthly_data[month] for month in sorted_months]
            
            # Format month labels (YYYY-MM to MMM YYYY)
            month_names = {
                '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun',
                '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
            }
            
            formatted_labels = []
            for month_key in sorted_months:
                year, month = month_key.split('-')
                formatted_labels.append(f"{month_names[month]} {year}")
            
            # Create line chart for monthly trends
            fig3, ax3 = plt.subplots(figsize=(8, 4), dpi=100)
            fig3.patch.set_facecolor('none')  # Transparent background
            
            # Plot the line
            ax3.plot(formatted_labels, monthly_amounts, marker='o', linestyle='-',
                     color='royalblue', linewidth=2, markersize=6)
            
            # Add data labels on each point
            for i, amount in enumerate(monthly_amounts):
                ax3.text(i, amount + (max(monthly_amounts) * 0.02), f'₹{amount:.0f}',
                        ha='center', va='bottom', fontsize=9,
                        color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            # Formatting
            ax3.set_title('Monthly Spending Trends',
                         color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            ax3.set_xlabel('Month', color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            ax3.set_ylabel('Amount (₹)', color='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            ax3.tick_params(colors='white' if ctk.get_appearance_mode() == "Dark" else 'black')
            
            # Rotate x-axis labels for better readability
            plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')
            
            # Add grid
            ax3.grid(True, alpha=0.3, linestyle='--')
            
            # Adjust layout
            plt.tight_layout()
            
            # Create canvas
            canvas3 = FigureCanvasTkAgg(fig3, master=monthly_frame)
            canvas3.draw()
            canvas3.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=10)
        else:
            no_data_label = ctk.CTkLabel(
                monthly_frame,
                text="No expense data available. Add some expenses to see trends.",
                font=self.normal_font
            )
            no_data_label.pack(pady=50)
        
        # Export Data Tab
        export_frame = tabview.tab("Export Data")
        
        # Export title
        export_title = ctk.CTkLabel(
            export_frame,
            text="Export your expense data to CSV format",
            font=self.normal_font
        )
        export_title.pack(pady=(30, 20), padx=20)
        
        # Export info frame
        export_info = ctk.CTkFrame(export_frame)
        export_info.pack(fill=tk.BOTH, expand=True, padx=40, pady=(0, 20))
        
        # Info label
        info_label = ctk.CTkLabel(
            export_info,
            text="You can export all your expenses to a CSV file.\nThe file will be saved in the application directory.\n\nCSV files can be opened in Excel, Google Sheets,\nor any spreadsheet application.",
            font=self.normal_font,
            justify=tk.LEFT
        )
        info_label.pack(pady=(30, 20), padx=30)
        
        # Export button
        def export_to_csv():
            expenses = self.db.get_all_expenses()
            
            if not expenses:
                messagebox.showinfo("No Data", "No expenses to export. Add some expenses first.")
                return
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"expenses_export_{timestamp}.csv"
            
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['Date', 'Description', 'Category', 'Amount']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    for expense in expenses:
                        writer.writerow({
                            'Date': expense['date'],
                            'Description': expense['description'] if expense['description'] else 'N/A',
                            'Category': expense['category'],
                            'Amount': expense['amount']
                        })
                
                messagebox.showinfo("Export Successful", f"Data exported successfully to:\n{filename}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export data: {str(e)}")
        
        export_btn = ctk.CTkButton(
            export_info,
            text="Export to CSV",
            font=self.normal_font,
            height=50,
            width=200,
            command=export_to_csv
        )
        export_btn.pack(pady=(10, 30))


def main():
    """Main entry point for the application."""
    app = ExpenseTrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
