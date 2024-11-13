import json
import random
import math
import pandas as pd
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Get a list of dances and members from the sheet without sorting or preferences
def get_dances(request):
    # Set CORS headers for preflight requests
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {'Access-Control-Allow-Origin': '*'}
    
    request_data = request.get_json(silent=True)
    if not request_data:
        return ('Invalid JSON payload', 400, headers)

    token = request_data.get('token')
    spreadsheet_id = request_data.get('spreadsheetId')
    sheet_name = request_data.get('sheetName')
    
    if not token or not spreadsheet_id or not sheet_name:
        return ('Missing token, spreadsheet ID, or sheet name', 400, headers)

    try:
        creds = Credentials(token)
        service = build('sheets', 'v4', credentials=creds)
        
        sheet_range = f"'{sheet_name}'"
        sheet = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=sheet_range).execute()
        data = sheet.get('values', [])
        
        if not data:
            return ('No data found in the sheet.', 400, headers)
        
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # Use read_data to parse out dances and members
        dances, members = read_data(df)
        
        return (json.dumps({'dances': dances, 'members': members}), 200, {**headers, 'Content-Type': 'application/json'})

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        print(error_message)
        return (error_message, 500, headers)


# Process and return the sorted dance list based on preferences
def process_request(request):
    # Set CORS headers for preflight requests
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {'Access-Control-Allow-Origin': '*'}

    request_data = request.get_json(silent=True)
    if not request_data:
        return ('Invalid JSON payload', 400, headers)

    token = request_data.get('token')
    spreadsheet_id = request_data.get('spreadsheetId')
    sheet_name = request_data.get('sheetName')
    preferences = request_data.get('preferences', {})

    if not token or not spreadsheet_id or not sheet_name:
        return ('Missing token, spreadsheet ID, or sheet name', 400, headers)

    try:
        creds = Credentials(token)
        service = build('sheets', 'v4', credentials=creds)
        
        sheet_range = f"'{sheet_name}'"
        sheet = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=sheet_range).execute()
        data = sheet.get('values', [])

        if not data:
            return ('No data found in the sheet.', 400, headers)
        
        df = pd.DataFrame(data[1:], columns=data[0])
        dances, members = read_data(df)
        
        # Run the simulated annealing algorithm with preferences applied
        results = []
        for _ in range(3):
            best_schedule, best_cost = simulated_annealing(dances, members, preferences=preferences)
            collision_details = get_collision_details(best_schedule, members)
            results.append({
                'schedule': best_schedule,
                'cost': best_cost,
                'collisions': collision_details
            })

        return (json.dumps({'results': results}), 200, {**headers, 'Content-Type': 'application/json'})

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        print(error_message)
        return (error_message, 500, headers)


# Reusable function to read dance data
def read_data(df):
    dances = []
    members = {}
    skip_section = False  # Flag to indicate if we're in the "NOT Included" section

    # Define possible column names
    dance_columns = ['Dance', 'Song Name']
    member_columns = ['Members', 'Members Participating', 'Member List']

    # Identify and rename columns to standard names
    dance_col = next((col for col in df.columns if col in dance_columns), None)
    member_col = next((col for col in df.columns if col in member_columns), None)

    if dance_col is None or member_col is None:
        raise ValueError("Could not find 'Dance' or 'Members' columns in the DataFrame")

    # Rename columns
    df = df.rename(columns={dance_col: 'Dance', member_col: 'Members'})

    # Iterate over the DataFrame rows
    for index, row in df.iterrows():
        dance_name = str(row['Dance']).strip()
        members_raw = str(row['Members']).strip()
        
        # Skip rows where 'Members' is empty or invalid
        if not members_raw or members_raw.lower() in ['nan', 'none']:
            continue

        # Skip rows where 'Dance' is empty or invalid
        if not dance_name or dance_name.lower() in ['nan', 'none']:
            continue

        # Check for 'NOT Included' section header
        if dance_name.lower() == 'not included':
            skip_section = True  # Start skipping dances
            continue

        if skip_section:
            continue  # Skip dances under 'NOT Included'

        # Process the dance
        member_list = [m.strip() for m in members_raw.split(',') if m.strip()]
        
        # If member_list is empty after processing, skip the row
        if not member_list:
            continue

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
        for member in dance_members:
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
        for member in dance_members:
            member_last_dance[member] = idx
    return collisions

def simulated_annealing(dances, members, preferences=None, max_iter=10000, initial_temp=1000, cooling_rate=0.003):
    # Extract preferences
    fixed_positions = preferences.get('fixedPositions', [])
    start_dances = preferences.get('Start', [])
    middle_dances = preferences.get('Middle', [])
    end_dances = preferences.get('End', [])

    # Initialize variables
    fixed_indices = {}
    available_dances = set(dances)

    # Assign fixed positions
    for item in fixed_positions:
        dance_name = item.get('name')
        position = item.get('position')
        if dance_name and position is not None:
            idx = int(position) - 1  # Convert to zero-based index
            fixed_indices[idx] = dance_name
            if dance_name in available_dances:
                available_dances.remove(dance_name)

    # Remove Start, Middle, End dances from available dances
    for dance in start_dances + middle_dances + end_dances:
        if dance in available_dances:
            available_dances.remove(dance)

    # Build the initial schedule
    schedule_length = len(dances)
    schedule = [None] * schedule_length

    # Place fixed position dances
    for idx, dance in fixed_indices.items():
        schedule[idx] = dance

    # Place Start dances at the beginning
    idx = 0
    for dance in start_dances:
        while schedule[idx] is not None:
            idx += 1
        schedule[idx] = dance
        idx += 1

    # Place End dances at the end
    idx = schedule_length - 1
    for dance in reversed(end_dances):
        while schedule[idx] is not None:
            idx -= 1
        schedule[idx] = dance
        idx -= 1

    # Remaining positions are for Middle dances and available dances
    middle_and_available = list(middle_dances) + list(available_dances)
    random.shuffle(middle_and_available)

    # Fill in the remaining positions
    for idx in range(schedule_length):
        if schedule[idx] is None:
            schedule[idx] = middle_and_available.pop()

    # Now, schedule is the initial schedule
    current_schedule = schedule[:]
    current_cost = calculate_collisions(current_schedule, members)
    best_schedule = current_schedule[:]
    best_cost = current_cost
    temp = initial_temp

    # Indices of dances that can be swapped (excluding fixed positions)
    swap_indices = [i for i in range(len(current_schedule)) if i not in fixed_indices]

    for iteration in range(max_iter):
        temp = temp * (1 - cooling_rate)
        if temp <= 0:
            break

        # Create a new neighbor by swapping two dances (excluding fixed positions)
        if len(swap_indices) < 2:
            break  # Not enough dances to swap

        idx1, idx2 = random.sample(swap_indices, 2)
        new_schedule = current_schedule[:]
        new_schedule[idx1], new_schedule[idx2] = new_schedule[idx2], new_schedule[idx1]
        new_cost = calculate_collisions(new_schedule, members)

        delta_cost = new_cost - current_cost
        if delta_cost < 0:
            acceptance_probability = 1.0
        else:
            acceptance_probability = math.exp(-delta_cost / temp)

        if acceptance_probability > random.random():
            current_schedule = new_schedule
            current_cost = new_cost
            if current_cost < best_cost:
                best_schedule = current_schedule[:]
                best_cost = current_cost

        if best_cost == 0:
            break

    return best_schedule, best_cost
