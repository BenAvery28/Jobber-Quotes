import sqlite3
from datetime import datetime

#sqlite database file name
DB_PATH = "jobber_calendar.db"


"""
    initializes the data base and ensure the "calander" table exists
    if table does not exist, it will be created.
    table elements: 
    - id: auto incremented primary key
    - name: customers name 
    - start_at: starting time of the appointment
    - end_at: ending time of the appointment
    - date: day of the appointment
"""
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        #
        # CHANGE IMMEDIATELY
        # add extra 'date' entry
        # add customer name entry (think about collisions)
        # change table name
        #
        conn.execute(""" CREATE TABLE IF NOT EXISTS visits ( id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL
            )
        """)


"""
    retrieve all the saved 'appointments' from the database
    returns a list of dictionaries with keys at start_at and end_at
"""
def get_visits():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT start_at, end_at FROM visits")
        return [{"startAt": start, "endAt": end} for start, end in cursor.fetchall()]


"""
    inserts a new appointment to the database
    params:
     - start_at (string): ISO timestamp of the start of the appointment
     - end_at (string): ISO timestamp of the end of the appointment
"""
def add_visit(start_at, end_at):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO visits (start_at, end_at) VALUES (?, ?)", (start_at, end_at))
        conn.commit()


"""
    removes customer from the table if they call off a visit
    params: 
    - name: the customers name
"""
def remove_appointment_by_name(name):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("DELETE FROM visits WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount


###############################################################
#                  TESTING UTILITIES                          #
###############################################################
"""
    Deletes all records from the appointment table
    Used for resseting db in 
"""
def clear_visits():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM visits")
        conn.commit()

