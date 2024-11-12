# main.py

import json
import random
import math
import pandas as pd
from flask import Flask, request, jsonify
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

# Simulated Annealing Algorithm and Helper Functions

def read_data(data, dance_column, member_column, exclude_section_headers):
    df = pd.DataFrame(data[1:], columns=data[0])  # Create DataFrame from data
    dances = []
    members = {}
    skip_section = False  # Flag to indicate if we're in the "NOT Included" section

    for index, row in df.iterrows():
        dance_name = str(row[dance_column]).strip()
        if dance_name == '':
            continue  # Skip empty rows

        # Check for section headers to skip
        if dance_name.lower() in exclude_section_headers:
            skip_section = True
            continue

        if skip_section:
            continue  # Skip dances under excluded sections

        # Process the dance
        member_list_raw = str(row[member_column])
        member_list = [m.strip() for m in member_list_raw.split(',') if m.strip()]
        dances.append(dance_name)
        members[dance_name] = member_list
    return dances, members

def calculate_collisions(schedule, members):
    collisions = 0
    member_last_dance = {}
    for idx, dance in enumerate(schedule):
        dance_members = members[dance]
        for member in dance_members:
            if member in member_last_dance and member_last_dance[member] == idx - 1:
                collisions += 1
            member_last_dance[member] = idx
    return collisions

def get_collision_details(schedule, members):
    collisions = []
    member_last_dance = {}
    for idx, dance in enumerate(schedule):
        dance_members = members[dance]
        for member in dance_members:
            if member in member_last_dance and member_last_dance[member] == idx - 1:
                # Collision detected
                previous_dance = schedule[idx - 1]
                collision_info = {
                    'member': member,
                    'previous_dance': previous_dance,
                    'current_dance': dance,
                    'positions': (idx, idx + 1)  # Zero-based positions
                }
                collisions.append(collision_info)
            member_last_dance[member] = idx
    return collisions

def simulated_annealing(dances, members, preferences=None, start_dance=None, end_dance=None,
                        max_iter=10000, initial_temp=1000, cooling_rate=0.003):
    # Remove start and end dances from the list if they are specified
    available_dances = dances[:]
    if start_dance and start_dance in available_dances:
        available_dances.remove(start_dance)
    if end_dance and end_dance in available_dances and end_dance != start_dance:
        available_dances.remove(end_dance)

    # Initialize with a random schedule
    current_schedule = available_dances[:]
    random.shuffle(current_schedule)

    # Add start and end dances at fixed positions
    if start_dance:
        current_schedule.insert(0, start_dance)
    if end_dance:
        current_schedule.append(end_dance)

    current_cost = calculate_collisions(current_schedule, members)
    best_schedule = current_schedule[:]
    best_cost = current_cost
    temp = initial_temp

    # Indices of dances that can be swapped (excluding fixed start and end)
    fixed_indices = set()
    if start_dance:
        fixed_indices.add(0)
    if end_dance:
        fixed_indices.add(len(current_schedule) - 1)

    swap_indices = [i for i in range(len(current_schedule)) if i not in fixed_indices]
    
    def preference_penalty(schedule):
        penalty = 0
        section_indices = {
            'Start': range(len(schedule) // 3),
            'Middle': range(len(schedule) // 3, 2 * len(schedule) // 3),
            'End': range(2 * len(schedule) // 3, len(schedule))
        }
        for section, dances_in_section in preferences.items():
            indices = section_indices.get(section, [])
            for dance in dances_in_section:
                if dance in schedule:
                    position = schedule.index(dance)
                    if position not in indices:
                        penalty += 1  # Add a penalty if the dance is not in the preferred section
        return penalty

    for iteration in range(max_iter):
        # Temperature decreases with each iteration
        temp = temp * (1 - cooling_rate)
        if temp <= 0:
            break

        # Create a new neighbor by swapping two dances (excluding fixed dances)
        new_schedule = current_schedule[:]
        idx1, idx2 = random.sample(swap_indices, 2)
        new_schedule[idx1], new_schedule[idx2] = new_schedule[idx2], new_schedule[idx1]
        new_cost = calculate_collisions(current_schedule, members) + preference_penalty(current_schedule)

        # Calculate acceptance probability
        delta_cost = new_cost - current_cost
        if delta_cost < 0:
            acceptance_probability = 1.0
        else:
            acceptance_probability = math.exp(-delta_cost / temp)

        # Decide whether to accept the new schedule
        if acceptance_probability > random.random():
            current_schedule = new_schedule
            current_cost = new_cost
            if current_cost < best_cost:
                best_schedule = current_schedule[:]
                best_cost = current_cost

        # Early exit if perfect schedule is found
        if best_cost == 0:
            break

    return best_schedule, best_cost

# Flask Route to Handle Requests

@app.route('/', methods=['POST'])
def process_request():
    request_data = request.get_json()

    # Get the OAuth token from the request
    token = request_data.get('token')
    if not token:
        return jsonify({'error': 'Missing OAuth token'}), 400

    # Get the spreadsheet ID and sheet name from the request
    spreadsheet_id = request_data.get('spreadsheetId')
    sheet_name = request_data.get('sheetName')
    if not spreadsheet_id or not sheet_name:
        return jsonify({'error': 'Missing spreadsheet ID or sheet name'}), 400
    
    preferences = request_data.get('preferences', {})
    
    # Get additional parameters
    dance_column = request_data.get('danceColumn', 'Dance')
    member_column = request_data.get('memberColumn', 'Members')
    exclude_section_headers = [header.lower() for header in request_data.get('excludeSectionHeaders', ['not included'])]

    start_dance = request_data.get('startDance')
    end_dance = request_data.get('endDance')

    # Create credentials and build the service
    creds = Credentials(token)
    service = build('sheets', 'v4', credentials=creds)

    # Read data from the specified sheet
    sheet_range = f"'{sheet_name}'"
    sheet = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=sheet_range).execute()
    data = sheet.get('values', [])

    if not data:
        return jsonify({'error': 'No data found in the sheet.'}), 400

    # Read and process the data
    dances, members = read_data(data, dance_column, member_column, exclude_section_headers)

    # Run the simulated annealing algorithm three times
    results = []
    for _ in range(3):
        schedule, cost = simulated_annealing(
            dances,
            members,
            preferences=preferences,
            start_dance=start_dance,
            end_dance=end_dance
        )
        collision_details = get_collision_details(schedule, members)
        results.append({
            'schedule': schedule,
            'cost': cost,
            'collisions': collision_details
        })

    # Return the results as JSON
    return jsonify({'results': results})

# Entry Point for Cloud Functions
def dance_sorter(request):
    return app(request)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'POST'
    return response

if __name__ == "__main__":
    app.run(debug=True)
