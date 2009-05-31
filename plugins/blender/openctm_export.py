#!BPY

"""
Name: 'OpenCTM (*.ctm)...'
Blender: 248
Group: 'Export'
Tooltip: 'Export active object to OpenCTM (compressed) format'
"""

import bpy
import Blender
from Blender import Mesh, Scene, Window, sys, Image, Draw
import BPyMesh
import ctypes
from ctypes import *
from ctypes.util import find_library
import os


__author__ = "Marcus Geelnard"
__version__ = "0.1"
__bpydoc__ = """\
This script exports OpenCTM files from Blender. It supports normals,
colours, and texture coordinates per vertex. Only one mesh can be exported
at a time.
"""

# Copyright (C) 2009: Marcus Geelnard
#
# This program is released to the public domain.
#
# Portions of this code are taken from ply_export.py in Blender
# 2.48.
#
# The script uses the OpenCTM shared library (.so, .dll, etc). If no
# such library can be found, the script will exit with an error
# message.
#
# v0.1, 2009-05-31
#    - First test version with an alpha version of the OpenCTM API
#


def file_callback(filename):
	
	if not filename.lower().endswith('.ctm'):
		filename += '.ctm'

	# Get object mesh from the selected object
	scn = bpy.data.scenes.active
	ob = scn.objects.active
	if not ob:
		Blender.Draw.PupMenu('Error%t|Select 1 active object')
		return
	mesh = BPyMesh.getMeshFromObject(ob, None, False, False, scn)
	if not mesh:
		Blender.Draw.PupMenu('Error%t|Could not get mesh data from active object')
		return

	# Check which mesh properties are present...
	hasVertexUV = mesh.vertexUV or mesh.faceUV
	hasVertexColors = mesh.vertexColors

	# Show a GUI for the export settings
	pupBlock = []
	EXPORT_APPLY_MODIFIERS = Draw.Create(1)
	pupBlock.append(('Apply Modifiers', EXPORT_APPLY_MODIFIERS, 'Use transformed mesh data.'))
	EXPORT_NORMALS = Draw.Create(1)
	pupBlock.append(('Normals', EXPORT_NORMALS, 'Export vertex normal data.'))
	if hasVertexUV:
		EXPORT_UV = Draw.Create(1)
		pupBlock.append(('UVs', EXPORT_UV, 'Export texface UV coords.'))
	if hasVertexColors:
		EXPORT_COLORS = Draw.Create(1)
		pupBlock.append(('Colors', EXPORT_COLORS, 'Export vertex Colors.'))
	EXPORT_MG2 = Draw.Create(0)
	pupBlock.append(('Fixed Point', EXPORT_MG2, 'Use limited precision algorithm (MG2 method = better compression).'))
	if not Draw.PupBlock('Export...', pupBlock):
		return

	# Adjust export settings according to GUI selections
	EXPORT_APPLY_MODIFIERS = EXPORT_APPLY_MODIFIERS.val
	EXPORT_NORMALS = EXPORT_NORMALS.val
	if hasVertexUV:
		EXPORT_UV = EXPORT_UV.val
	else:
		EXPORT_UV = False
	if hasVertexColors:
		EXPORT_COLORS = EXPORT_COLORS.val
	else:
		EXPORT_COLORS = False
	EXPORT_MG2 = EXPORT_MG2.val

	is_editmode = Blender.Window.EditMode()
	if is_editmode:
		Blender.Window.EditMode(0, '', 0)
	Window.WaitCursor(1)
	try:
		# Get the mesh, again, if we wanted modifiers (from GUI selection)
		if EXPORT_APPLY_MODIFIERS:
			mesh = BPyMesh.getMeshFromObject(ob, None, EXPORT_APPLY_MODIFIERS, False, scn)
			if not mesh:
				Blender.Draw.PupMenu('Error%t|Could not get mesh data from active object')
				return
			mesh.transform(ob.matrixWorld, True)

		# Count triangles (quads count as two triangles)
		triangleCount = 0
		for f in mesh.faces:
			if len(f.v) == 4:
				triangleCount += 2
			else:
				triangleCount += 1

		# Extract indices from the Blender mesh (quads are split into two triangles)
		pindices = cast((c_int * 3 * triangleCount)(), POINTER(c_int))
		i = 0
		for f in mesh.faces:
			pindices[i] = c_int(f.v[0].index)
			pindices[i + 1] = c_int(f.v[1].index)
			pindices[i + 2] = c_int(f.v[2].index)
			i += 3
			if len(f.v) == 4:
				pindices[i] = c_int(f.v[0].index)
				pindices[i + 1] = c_int(f.v[2].index)
				pindices[i + 2] = c_int(f.v[3].index)
				i += 3

		# Extract vertex array from the Blender mesh
		vertexCount = len(mesh.verts)
		pvertices = cast((c_float * 3 * vertexCount)(), POINTER(c_float))
		i = 0
		for v in mesh.verts:
			pvertices[i] = c_float(v.co.x)
			pvertices[i + 1] = c_float(v.co.y)
			pvertices[i + 2] = c_float(v.co.z)
			i += 3

		# Extract normals
		if EXPORT_NORMALS:
			pnormals = cast((c_float * 3 * vertexCount)(), POINTER(c_float))
			i = 0
			for v in mesh.verts:
				pnormals[i] = c_float(v.no.x)
				pnormals[i + 1] = c_float(v.no.y)
				pnormals[i + 2] = c_float(v.no.z)
				i += 3
		else:
			pnormals = POINTER(c_float)()

		# Extract UVs
		if EXPORT_UV:
			ptexCoords = cast((c_float * 2 * vertexCount)(), POINTER(c_float))
			if mesh.faceUV:
				for f in mesh.faces:
					for j, v in enumerate(f.v):
						k = v.index
						if k < vertexCount:
							uv = f.uv[j]
							ptexCoords[k * 2] = uv[0]
							ptexCoords[k * 2 + 1] = uv[1]
			else:
				i = 0
				for v in mesh.verts:
					ptexCoords[i] = c_float(v.uvco[0])
					ptexCoords[i + 1] = c_float(v.uvco[1])
					i += 2
		else:
			ptexCoords = POINTER(c_float)()

		# Extract colors
		if EXPORT_COLORS:
			pcolors = cast((c_float * 4 * vertexCount)(), POINTER(c_float))
			for f in mesh.faces:
				for j, v in enumerate(f.v):
					k = v.index
					if k < vertexCount:
						col = f.col[j]
						pcolors[k * 4] = col.r / 256.0
						pcolors[k * 4 + 1] = col.g / 256.0
						pcolors[k * 4 + 2] = col.b / 256.0
						pcolors[k * 4 + 3] = 1.0
		else:
			pcolors = POINTER(c_float)()

		# Load the OpenCTM shared library
		if os.name == 'nt':
			libHDL = WinDLL('openctm.dll')
		else:
			libName = find_library('openctm')
			if not libName:
				Blender.Draw.PupMenu('Could not find the OpenCTM shared library')
				return
			libHDL = CDLL(libName)
		if not libHDL:
			Blender.Draw.PupMenu('Could not open the OpenCTM shared library')
			return

		# Get all the functions from the shared library that we need
		ctmNewContext = libHDL.ctmNewContext
		ctmNewContext.argtypes = [c_int]
		ctmNewContext.restype = c_void_p
		ctmFreeContext = libHDL.ctmFreeContext
		ctmFreeContext.argtypes = [c_void_p]
		ctmFileComment = libHDL.ctmFileComment
		ctmFileComment.argtypes = [c_void_p, c_char_p]
		ctmDefineMesh = libHDL.ctmDefineMesh
		ctmDefineMesh.argtypes = [c_void_p, POINTER(c_float), c_int, POINTER(c_int), c_int, POINTER(c_float)]
		ctmSave = libHDL.ctmSave
		ctmSave.argtypes = [c_void_p, c_char_p]
		ctmAddTexMap = libHDL.ctmAddTexMap
		ctmAddTexMap.argtypes = [c_void_p, POINTER(c_float), c_char_p]
		ctmAddTexMap.restype = c_int
		ctmAddAttribMap = libHDL.ctmAddAttribMap
		ctmAddAttribMap.argtypes = [c_void_p, POINTER(c_float), c_char_p]
		ctmAddAttribMap.restype = c_int
		ctmCompressionMethod = libHDL.ctmCompressionMethod
		ctmCompressionMethod.argtypes = [c_void_p, c_int]
		ctmVertexPrecisionRel = libHDL.ctmVertexPrecisionRel
		ctmVertexPrecisionRel.argtypes = [c_void_p, c_float]

		# Create an OpenCTM context
		ctm = ctmNewContext(0x0102)  # CTM_EXPORT
		try:
			# Set the file comment
			ctmFileComment(ctm, c_char_p('%s - created by Blender %s (www.blender.org)' % (ob.getName(), Blender.Get('version'))))

			# Define the mesh
			ctmDefineMesh(ctm, pvertices, c_int(vertexCount), pindices, c_int(triangleCount), pnormals)

			# Add texture coordinates?
			if EXPORT_UV:
				ctmAddTexMap(ctm, ptexCoords, c_char_p())

			# Add colors?
			if EXPORT_COLORS:
				ctmAddAttribMap(ctm, pcolors, c_char_p('Colors'))

			# Set compression method
			if EXPORT_MG2:
				ctmCompressionMethod(ctm, 0x0203)  # CTM_METHOD_MG2
				ctmVertexPrecisionRel(ctm, 0.01)
			else:
				ctmCompressionMethod(ctm, 0x0202)  # CTM_METHOD_MG1

			# Save the file
			ctmSave(ctm, c_char_p(filename))
		finally:
			# Free the OpenCTM context
			ctmFreeContext(ctm)

	finally:
		Window.WaitCursor(0)
		if is_editmode:
			Blender.Window.EditMode(1, '', 0)

def main():
	Blender.Window.FileSelector(file_callback, 'Export OpenCTM', Blender.sys.makename(ext='.ctm'))

if __name__=='__main__':
	main()