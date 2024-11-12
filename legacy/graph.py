import networkx as nx
import matplotlib.pyplot as plt
import pandas as pd

# Load the data
df = pd.read_csv('loko_performances_maf.csv')

# Clean up the DataFrame: remove unnecessary rows and handle dancer lists
df_clean = df.dropna(subset=['Dance', 'Members'])  # Only keep rows with valid dances and members

# Create a graph
G = nx.Graph()

# Add nodes and edges based on shared dancers
for i, row in df_clean.iterrows():
    dance = row['Dance']
    members = [member.strip() for member in row['Members'].split(',')]  # Split and clean member names
    G.add_node(dance, members=members)
    
    # Compare with all other dances and create edges based on shared members
    for j, other_row in df_clean.iterrows():
        if i != j:
            other_dance = other_row['Dance']
            other_members = [member.strip() for member in other_row['Members'].split(',')]
            # Check for shared dancers
            if set(members) & set(other_members):
                G.add_edge(dance, other_dance)

# Plotting the graph
plt.figure(figsize=(10, 10))
pos = nx.spring_layout(G, seed=42)  # Spring layout for better visualization
nx.draw(G, pos, with_labels=True, node_color='skyblue', node_size=2000, font_size=10, font_weight='bold', edge_color='gray')

# Display graph
plt.title("Dance Team Graph (Shared Dancers)")
plt.show()
