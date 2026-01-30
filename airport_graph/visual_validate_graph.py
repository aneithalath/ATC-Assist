import os
import pickle
import sys
import math
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx

# Paths
GRAPH_PATH = os.path.join(os.path.dirname(__file__), '../airport_data/kphx_graph.pkl')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'outputs')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load graph
def load_graph(path):
    with open(path, 'rb') as f:
        G = pickle.load(f)
    # If G is a dict, try to convert to a NetworkX graph
    if isinstance(G, dict):
        # Try to infer directed/undirected
        if 'nodes' in G and 'edges' in G:
            H = nx.DiGraph()
            for n, data in G['nodes'].items():
                H.add_node(n, **data)
            for u, v, data in G['edges']:
                H.add_edge(u, v, **data)
            return H
        else:
            raise TypeError('Loaded pickle is a dict but not a recognized graph format.')
    if not isinstance(G, (nx.Graph, nx.DiGraph)):
        # Try to extract underlying graph if it's a custom AirportGraph class
        # Common attribute names: 'graph', '_graph', 'nx_graph'
        for attr in ['graph', '_graph', 'nx_graph']:
            if hasattr(G, attr):
                nxg = getattr(G, attr)
                if isinstance(nxg, (nx.Graph, nx.DiGraph)):
                    return nxg
        # Try to convert if it has node/edge iterators
        if hasattr(G, 'nodes') and hasattr(G, 'edges'):
            try:
                H = nx.DiGraph()
                for n in G.nodes:
                    data = G.nodes[n] if hasattr(G.nodes, '__getitem__') else {}
                    # If data is not a dict, try to convert
                    if not isinstance(data, dict):
                        if hasattr(data, '__dict__'):
                            data = dict(data.__dict__)
                        else:
                            data = {}
                    H.add_node(n, **data)
                # Try to iterate edges as (u, v) or (u, v, data)
                # If G.edges is a dict, try to extract endpoints and data from values
                if isinstance(G.edges, dict):
                    for edge_id, edge_obj in G.edges.items():
                        # Try to extract u, v, data from edge_obj
                        # Common attribute names: 'u', 'v', 'source', 'target', 'data', etc.
                        u = (
                            getattr(edge_obj, 'u', None)
                            or getattr(edge_obj, 'source', None)
                            or getattr(edge_obj, 'start_node', None)
                        )
                        v = (
                            getattr(edge_obj, 'v', None)
                            or getattr(edge_obj, 'target', None)
                            or getattr(edge_obj, 'end_node', None)
                        )
                        if u is None or v is None:
                            raise TypeError(f'Cannot extract endpoints from edge object: {edge_obj}')
                        # Edge data
                        if hasattr(edge_obj, '__dict__'):
                            data = dict(edge_obj.__dict__)
                        else:
                            data = {}
                        H.add_edge(u, v, **data)
                    return H
                # Fallback to previous logic for other types
                edges_iter = G.edges
                if callable(edges_iter):
                    edges_iter = edges_iter()
                try:
                    for item in edges_iter:
                        if isinstance(item, tuple) and len(item) == 3:
                            u, v, data = item
                        elif isinstance(item, tuple) and len(item) == 2:
                            u, v = item
                            data = G.edges[u, v] if hasattr(G.edges, '__getitem__') else {}
                        else:
                            raise TypeError(f'Edge item not a tuple of (u,v) or (u,v,data): {item}')
                        if not isinstance(data, dict):
                            if hasattr(data, '__dict__'):
                                data = dict(data.__dict__)
                            else:
                                data = {}
                        H.add_edge(u, v, **data)
                except Exception as e:
                    print(f"Edge conversion failed: {e}", file=sys.stderr)
                    raise
                return H
            except Exception as e:
                raise TypeError(f'Could not convert custom graph object: {e}')
        raise TypeError(f'Loaded object is not a NetworkX graph, got {type(G)} and no conversion found')
    return G

def fail(msg):
    print(f'FAIL: {msg}', file=sys.stderr)
    sys.exit(1)

def check_graph(G):
    # 1. Has nodes and edges
    # Defensive: check for correct type
    if not hasattr(G, 'nodes') or not hasattr(G, 'edges'):
        fail(f'Graph object missing nodes/edges attributes (type={type(G)})')
    if len(G.nodes) == 0 or len(G.edges) == 0:
        fail('Graph has no nodes or edges')
    # 2. Node coordinates sanity
    for n in G.nodes:
        data = G.nodes[n]
        x, y = data.get('x'), data.get('y')
        if x is None or y is None:
            fail(f'Node {n} missing coordinates')
        if not np.isfinite(x) or not np.isfinite(y):
            fail(f'Node {n} has non-finite coordinates')
    # 3. Edge length sanity
    for u, v in G.edges:
        data = G.edges[u, v]
        if u not in G.nodes or v not in G.nodes:
            fail(f'Edge ({u},{v}) references invalid node')
        x1, y1 = G.nodes[u]['x'], G.nodes[u]['y']
        x2, y2 = G.nodes[v]['x'], G.nodes[v]['y']
        dist = math.hypot(x2 - x1, y2 - y1)
        if dist < 0.5:
            fail(f'Edge ({u},{v}) has near-zero length: {dist:.3f} m')
        etype = data.get('type')
        if etype not in {'runway', 'taxiway'}:
            fail(f'Edge ({u},{v}) has invalid type: {etype}')
    # 4. One dominant connected component
    if not nx.is_connected(G.to_undirected()):
        # Check for one dominant component
        comps = sorted(nx.connected_components(G.to_undirected()), key=len, reverse=True)
        if len(comps) > 1 and len(comps[0]) < 0.9 * sum(len(c) for c in comps):
            fail('No dominant connected component')

# Plot 1: Full airport surface layout
def plot_surface_layout(G, out_path):
    fig, ax = plt.subplots(figsize=(10, 10))
    for u, v in G.edges:
        data = G.edges[u, v]
        x1, y1 = G.nodes[u]['x'], G.nodes[u]['y']
        x2, y2 = G.nodes[v]['x'], G.nodes[v]['y']
        if data['type'] == 'runway':
            ax.plot([x1, x2], [y1, y2], color='black', linewidth=2.5, zorder=2)
        else:
            ax.plot([x1, x2], [y1, y2], color='lightgray', linewidth=0.7, zorder=1)
    ax.set_aspect('equal')
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close(fig)

# Plot 2: Connected component highlight
def plot_connectivity(G, out_path):
    fig, ax = plt.subplots(figsize=(10, 10))
    UG = G.to_undirected()
    comps = sorted(nx.connected_components(UG), key=len, reverse=True)
    main = comps[0]
    # Plot main component
    for u, v in G.edges:
        data = G.edges[u, v]
        if u in main and v in main:
            color = 'black' if data['type'] == 'runway' else 'gray'
            lw = 2.5 if data['type'] == 'runway' else 0.7
            ax.plot([G.nodes[u]['x'], G.nodes[v]['x']], [G.nodes[u]['y'], G.nodes[v]['y']], color=color, linewidth=lw, zorder=2)
    # Plot other components
    for comp in comps[1:]:
        for u in comp:
            for v in G.neighbors(u):
                if v in comp and u < v:
                    data = G.get_edge_data(u, v)
                    if data:
                        color = 'red'
                        lw = 2.5
                        ax.plot([G.nodes[u]['x'], G.nodes[v]['x']], [G.nodes[u]['y'], G.nodes[v]['y']], color=color, linewidth=lw, zorder=3)
    ax.set_aspect('equal')
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close(fig)

# Plot 3: Edge-type separation
def plot_edge_type_separation(G, out_path):
    fig, ax = plt.subplots(figsize=(10, 10))
    # Taxiways
    for u, v in G.edges:
        data = G.edges[u, v]
        if data['type'] == 'taxiway':
            ax.plot([G.nodes[u]['x'], G.nodes[v]['x']], [G.nodes[u]['y'], G.nodes[v]['y']], color='dodgerblue', linewidth=0.7, label='Taxiway' if 'Taxiway' not in ax.get_legend_handles_labels()[1] else "")
    # Runways
    for u, v in G.edges:
        data = G.edges[u, v]
        if data['type'] == 'runway':
            ax.plot([G.nodes[u]['x'], G.nodes[v]['x']], [G.nodes[u]['y'], G.nodes[v]['y']], color='orange', linewidth=2.5, label='Runway' if 'Runway' not in ax.get_legend_handles_labels()[1] else "")
    ax.set_aspect('equal')
    ax.axis('off')
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc='upper right')
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close(fig)

def main():
    G = load_graph(GRAPH_PATH)
    print(f"Loaded AirportGraph: {len(G.nodes):,} nodes, {len(G.edges):,} edges")
    check_graph(G)
    print("Automated checks passed")
    plot_surface_layout(G, os.path.join(OUTPUT_DIR, 'airport_surface_layout.png'))
    plot_connectivity(G, os.path.join(OUTPUT_DIR, 'connectivity_check.png'))
    plot_edge_type_separation(G, os.path.join(OUTPUT_DIR, 'edge_type_separation.png'))
    print(f"Saved visual outputs to airport_graph/outputs/")
    # Show plots interactively
    for fname in ['airport_surface_layout.png', 'connectivity_check.png', 'edge_type_separation.png']:
        img = plt.imread(os.path.join(OUTPUT_DIR, fname))
        plt.figure(figsize=(8, 8))
        plt.imshow(img)
        plt.axis('off')
        plt.tight_layout()
        plt.show()

if __name__ == '__main__':
    main()
