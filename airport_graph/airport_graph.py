from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
import math
import shapely.geometry
import shapely.ops
import pyproj

# Node and Edge dataclasses
@dataclass(frozen=True)
class AirportNode:
    id: int
    x: float
    y: float
    connected_edges: Tuple[int, ...]

@dataclass(frozen=True)
class AirportEdge:
    id: int
    start_node: int
    end_node: int
    length_m: float
    ref: Optional[str]
    type: str  # 'runway' or 'taxiway'
    directionality: str = "bidirectional"

@dataclass(frozen=True)
class AirportGraph:
    nodes: Dict[int, AirportNode]
    edges: Dict[int, AirportEdge]

    @staticmethod
    def build_from_geojson(geojson: dict) -> 'AirportGraph':
        """
        Build AirportGraph from GeoJSON FeatureCollection.
        Only includes features with aeroway in {'runway', 'taxiway'} and LineString/MultilineString geometry.
        """
        # 1. Collect all relevant features
        features = [
            f for f in geojson.get('features', [])
            if f.get('properties', {}).get('aeroway') in {'runway', 'taxiway'}
            and f.get('geometry', {}).get('type') in {'LineString', 'MultiLineString'}
        ]
        # 2. Projector: local projection centered on airport
        # Find centroid of all coordinates
        all_coords = []
        for feat in features:
            geom = feat['geometry']
            if geom['type'] == 'LineString':
                all_coords.extend(geom['coordinates'])
            elif geom['type'] == 'MultiLineString':
                for line in geom['coordinates']:
                    all_coords.extend(line)
        lons, lats = zip(*all_coords)
        lon0, lat0 = sum(lons)/len(lons), sum(lats)/len(lats)
        proj = pyproj.Transformer.from_crs(
            f"epsg:4326",
            pyproj.CRS.from_proj4(f"+proj=tmerc +lat_0={lat0} +lon_0={lon0} +k=1 +x_0=0 +y_0=0 +datum=WGS84"),
            always_xy=True
        )
        def project(coord):
            x, y = proj.transform(coord[0], coord[1])
            return (x, y)
        # 3. Node deduplication (within 0.5m)
        node_lookup = {}
        node_coords = []
        node_id_counter = 0
        def find_or_add_node(x, y):
            for nid, (nx, ny) in enumerate(node_coords):
                if math.hypot(x-nx, y-ny) < 0.5:
                    return nid
            nonlocal node_id_counter
            node_coords.append((x, y))
            node_id = node_id_counter
            node_id_counter += 1
            return node_id
        edge_list = []
        edge_id_counter = 0
        edge_refs = []
        edge_types = []
        edge_nodes = []
        # 4. Build edges and nodes
        for feat in features:
            typ = feat['properties']['aeroway']
            ref = feat['properties'].get('ref')
            geom = feat['geometry']
            lines = []
            if geom['type'] == 'LineString':
                lines = [geom['coordinates']]
            elif geom['type'] == 'MultiLineString':
                lines = geom['coordinates']
            for line in lines:
                for i in range(len(line)-1):
                    p1 = project(line[i])
                    p2 = project(line[i+1])
                    n1 = find_or_add_node(*p1)
                    n2 = find_or_add_node(*p2)
                    if n1 == n2:
                        continue  # Skip degenerate/self-loop edge
                    length = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                    edge_nodes.append((n1, n2))
                    edge_refs.append(ref)
                    edge_types.append(typ)
                    edge_list.append(length)
        # 5. Build node->edges mapping
        node_edges: Dict[int, List[int]] = {i: [] for i in range(len(node_coords))}
        for eid, (n1, n2) in enumerate(edge_nodes):
            node_edges[n1].append(eid)
            node_edges[n2].append(eid)
        # 6. Create AirportNode and AirportEdge objects
        nodes = {
            nid: AirportNode(
                id=nid,
                x=coord[0],
                y=coord[1],
                connected_edges=tuple(node_edges[nid])
            )
            for nid, coord in enumerate(node_coords)
        }
        edges = {
            eid: AirportEdge(
                id=eid,
                start_node=n1,
                end_node=n2,
                length_m=edge_list[eid],
                ref=edge_refs[eid],
                type=edge_types[eid],
                directionality="bidirectional"
            )
            for eid, (n1, n2) in enumerate(edge_nodes)
        }
        return AirportGraph(nodes=nodes, edges=edges)
