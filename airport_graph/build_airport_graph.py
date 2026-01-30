import json
import pickle
from pathlib import Path
from airport_graph import AirportGraph

def main():
    geojson_path = Path(__file__).parent.parent / 'airport_data' / 'kphx.geojson'
    output_path = Path(__file__).parent.parent / 'airport_data' / 'kphx_graph.pkl'
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson = json.load(f)
    graph = AirportGraph.build_from_geojson(geojson)
    with open(output_path, 'wb') as f:
        pickle.dump(graph, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"AirportGraph built and saved to {output_path}")

if __name__ == '__main__':
    main()
