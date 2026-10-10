"""Conditional corner mapping to project client pixels, without InputGeometry."""
import numpy as np
import copy
from .read_dye_window_mapping import _fingerprint


def map_unity_geometry_to_client(geometry,window,screen,*,pixel_mapping=None):
 if (geometry.get('screen_origin')!='unity_bottom_left' or geometry.get('axis_aligned_candidate') is not True
     or window.get('source')!='win32_client_physical' or window.get('physical_coordinates') is not True
     or window.get('minimized') is not False or window.get('visible') is not True
     or screen.get('source')!='current_build_native_screen_fields'):
  raise ValueError('Unsupported coordinate sources/geometry')
 size=np.asarray(window.get('client_size_physical'),dtype=float)
 extent=np.asarray(screen.get('size'),dtype=float);origin=np.asarray(window.get('client_origin_physical'),dtype=float)
 if any(v.shape!=(2,) or not np.isfinite(v).all() for v in (size,extent,origin)) or np.any(size<=0):
  raise ValueError('Invalid window/screen coordinates')
 equal=bool(np.array_equal(size,extent))
 if not equal:
  if (not isinstance(pixel_mapping,dict) or pixel_mapping.get('source')!='win32_target_awareness_pixel_lattice'
      or pixel_mapping.get('coordinate_validation',{}).get('verified') is not True
      or pixel_mapping.get('physical_client_size')!=size.tolist()
      or pixel_mapping.get('native_screen_size')!=extent.tolist()
      or pixel_mapping.get('target_client_size')!=extent.tolist()):
   raise ValueError('Unity and physical client extents differ; verified pixel mapping required')
 corners=np.asarray(geometry.get('predicted_unity_corners'),dtype=float)
 if corners.shape!=(4,2) or not np.isfinite(corners).all():raise ValueError('Four finite corner candidates required')
 low=corners.min(axis=0);high=corners.max(axis=0)
 expected=np.asarray([[low[0],low[1]],[high[0],low[1]],[low[0],high[1]],[high[0],high[1]]])
 if np.any(high<=low) or np.max(np.abs(corners-expected))>1e-3:
  raise ValueError('Corner candidates are not an ordered axis-aligned rectangle')
 if np.any(low<0) or np.any(high>extent):raise ValueError('Board candidate lies outside client extent')
 native=corners.copy();native[:,1]=extent[1]-corners[:,1]
 client=native*(size/extent)
 desktop=client+origin
 client_board=[float(client[:,0].min()),float(client[:,1].min()),float(client[:,0].max()),float(client[:,1].max())]
 desktop_board=[client_board[0]+origin[0],client_board[1]+origin[1],client_board[2]+origin[0],client_board[3]+origin[1]]
 result=dict(client_corner_candidates=client.tolist(),desktop_corner_candidates=desktop.tolist(),
  client_board_candidate=client_board,desktop_board_candidate=desktop_board,
  extent_one_to_one=equal,continuous_edge_coordinates=True,dpi_multiplier_applied=not equal,
  runtime_measurement_verified=False,screen_geometry_available=False,ready_for_input=False,
  scope='Native cached continuous edges projected into measured physical client; mouse uses separately verified integer lattice')
 if pixel_mapping is not None:
  packet=copy.deepcopy(pixel_mapping)
  packet['native_board_top_left']=[float(native[:,0].min()),float(native[:,1].min()),float(native[:,0].max()),float(native[:,1].max())]
  packet.setdefault('viewport_origin',[0,0]);packet.setdefault('viewport_scale',[1.,1.])
  packet['mapping_sha256']=_fingerprint(packet)
  result['pixel_mapping']=packet
 return result
