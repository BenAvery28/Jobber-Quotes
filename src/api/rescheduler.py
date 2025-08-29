# src/api/rescheduler.py
#
# Handles automatic rescheduling when:
# 1. Customer cancels appointment
# 2. Weather changes and makes scheduled jobs unsuitable
# 3. Shifts all affected jobs to next available suitable slots
