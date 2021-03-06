# -*- coding: utf-8 -*-
"""
Created on Sun May  1 23:47:03 2016

@author: cjs14
"""
from io import BytesIO
import numpy as np
from six import string_types

from IPython.display import Image as ipy_Image
from PIL import Image, ImageChops, ImageDraw, ImageFont

from ..shared.colors import get as str_to_colour
from ..shared import fonts
from ..shared import get_data_path
from .opengl.qtviewer import QtViewer
from .opengl.renderers.line import LineRenderer
from .opengl.renderers.atom import AtomRenderer
from .opengl.renderers.triangle import TriangleRenderer
from .opengl.renderers.box import BoxRenderer
from .opengl.renderers.hexagon import HexagonRenderer
from .opengl.renderers.bond import BondRenderer
#from .opengl.postprocessing import (FXAAEffect, GammaCorrectionEffect, 
#                                             OutlineEffect, SSAOEffect)

##TODO simplify, change to MVC pattern
class Visualise_Sim(object):
    """ 
    A class to visualise atom data    
    """
    _unit_dict = {'real':{'distance':0.1}}
    
    def __init__(self, units='real'):
        """
        For units *real*, these are the units:
        
            mass = grams/mole
            distance = Angstroms
            time = femtoseconds
            energy = Kcal/mole
            velocity = Angstroms/femtosecond
            force = Kcal/mole-Angstrom
            torque = Kcal/mole
            temperature = Kelvin
            pressure = atmospheres
            dynamic viscosity = Poise
            charge = multiple of electron charge (1.0 is a proton)
            dipole = charge*Angstroms
            electric field = volts/Angstrom
            density = gram/cm^dim
        """
        assert units=='real', 'currently only supports real units'
        self._units = units
        
        # rendered objects
        self._atoms = []
        self._bonds = []
        self._boxes = []
        self._hexagons = []
        self._axes = None
        self._triangles = []
        
    def remove_all_objects(self):
        self._atoms = []
        self._bonds = []
        self._boxes = []
        self._hexagons = []
        self._axes = None
        self._triangles = []                
                
    def add_atoms(self, atoms_df, spheres=True, illustrate=False):
        """ add atoms to visualisation

        atoms_df : pandas.DataFrame
            a table of atom data, must contain columns;  
            x, y, z, radius, color and transparency
        spheres : bool
            whether the atoms are rendered as spheres or points
        illustrate : str
            if True, atom shading is more indicative of an illustration
        """
        assert set(['x','y','z','radius','color','transparency']).issubset(set(atoms_df.columns))
        
        r_array = np.array(atoms_df[['x','y','z']])
        r_array = self._unit_conversion(r_array, 'distance')
        
        radii = np.array(atoms_df['radius'])
        radii = self._unit_conversion(radii, 'distance')
        
        cols = atoms_df['color'].apply(
                lambda x: str_to_colour(x) if isinstance(x,string_types) else list(x) + [255]).tolist()
        if None in cols:
            raise ValueError('one or more colors not found')
        cols = np.array(cols)
        alphas = np.array(atoms_df['transparency'])
        
        #type_array = atoms_df['type'].map(lambda x: type_map.get(x,x)).tolist()
        
        backend = 'impostors' if spheres else 'points'
        
        shading = 'toon' if illustrate else 'phong'
        
        assert max(alphas) <= 1. and min(alphas) > 0., 'transparency must be between 0 and 1'

        self._atoms.append([r_array, radii, cols, alphas, backend, shading])   
        
    def remove_atoms(self, n=1):
        """ remove the last n sets of atoms to be added """
        assert len(self._atoms) >= n
        self._atoms = self._atoms[:-n]
    
    ##TODO start/end bonds at atom radii
    def add_bonds(self, atoms_df, bonds_df, 
                  cylinders=False, illustrate=False, linewidth=5):
        """ add bonds to visualisation

        atoms_df : pandas.DataFrame
            a table of atom data, must contain columns; x, y, z
        bonds_df : list
            a table of bond data, must contain; start, end, radius, color, transparency
            to/from refer to the atoms_df iloc (not necessarily the index number!)
        cylinders : bool
            whether the bonds are rendered as cylinders or lines
        illustrate : str
            if True, atom shading is more indicative of an illustration
        """
        assert set(['x','y','z','radius','color','transparency']).issubset(set(atoms_df.columns))
        assert set(['start','end','radius','transparency']).issubset(set(bonds_df.columns))
        assert (set(['color']).issubset(set(bonds_df.columns)) or 
                set(['color_start','color_end']).issubset(set(bonds_df.columns)))       
        
        r_array = np.array(atoms_df[['x','y','z']])
        r_array = self._unit_conversion(r_array, 'distance')
        
        #bounds = np.empty((bonds_df.shape[0], 2, 3))   
        #bounds[:, 0, :] = r_array[bonds_df.start.values]
        #bounds[:, 1, :] = r_array[bonds_df.end.values]
        starts = r_array[bonds_df.start.values]
        ends = r_array[bonds_df.end.values]
        
        radii = np.array(bonds_df['radius'])
        radii = self._unit_conversion(radii, 'distance')

        def get_colors(name):       
            cols = bonds_df[name].apply(
                    lambda x: str_to_colour(x) if isinstance(x,string_types) else list(x) + [255]).tolist()
            if None in cols:
                raise ValueError('one or more colors not found')
            cols = np.array(cols)
            return cols
        
        if 'color_start' in bonds_df.columns and 'color_end' in bonds_df.columns:
            col_start = get_colors('color_start')
            col_end = get_colors('color_end')
        else:
            col_start = get_colors('color')
            col_end = col_start
        

        alphas = np.array(bonds_df['transparency'])
        
        backend = 'impostors' if cylinders else 'lines'
        
        shading = 'toon' if illustrate else 'phong'
        
        assert max(alphas) <= 1. and min(alphas) > 0., 'transparency must be between 0 and 1'

        self._bonds.append([starts, ends, radii, col_start, col_end, 
                            alphas, backend, shading,linewidth])           

    def remove_bonds(self, n=1):
        """ remove the last n sets of bonds to be added """
        assert len(self._bonds) >= n
        self._bonds = self._bonds[:-n]
    
    def add_box(self, a,b,c, origin=[0,0,0], color='black', width=1):
        """ add wireframed box to visualisation
        
       a : np.ndarray(3, dtype=float)
          The a vectors representing the sides of the box.
       b : np.ndarray(3, dtype=float)
          The b vectors representing the sides of the box.
       c : np.ndarray(3, dtype=float)
          The c vectors representing the sides of the box.
       origin : np.ndarray((3,3), dtype=float), default to zero
          The origin of the box.
        color : str
          the color of the wireframe, in chemlab colors
          
        """
        vectors = self._unit_conversion(np.array([a,b,c]), 'distance')
        origin = self._unit_conversion(np.array(origin), 'distance')
        color = str_to_colour(color)
        
        self._boxes.append([vectors, origin, color, width])

    def add_box_from_meta(self,meta, color='black', width=1):
        """ a shortcut for adding boxes using a panda.Series containing a,b,c,origin
        """
        self.add_box(meta.a,meta.b,meta.c,meta.origin,color,width)

    def remove_boxes(self, n=1):
        """ remove the last n boxes to be added """
        assert len(self._boxes) >= n
        self._boxes = self._boxes[:-n]

    #TODO change vectors to a,b,c
    def add_hexagon(self, vectors, origin=np.zeros(3), color='black', width=1):
        """ add wireframed hexagonal prism to visualisation
        
       vectors : np.ndarray((2,3), dtype=float)
          The two vectors representing the orthogonal a,c directions.
       origin : np.ndarray((3,3), dtype=float), default to zero
          The origin of the hexagon (representing center of hexagon)
        color : str
          the color of the wireframe, in chemlab colors
          
        """
        vectors = self._unit_conversion(np.array(vectors), 'distance')
        origin = self._unit_conversion(np.array(origin), 'distance')
        color = str_to_colour(color)
        
        self._hexagons.append([vectors, origin, color, width])

    def remove_hexagons(self, n=1):
        """ remove the last n boxes to be added """
        assert len(self._hexagons) >= n
        self._hexagons = self._hexagons[:-n]

    def add_axes(self, axes=[[1,0,0],[0,1,0],[0,0,1]], 
                 length=1., offset=(-1.2,0.2), colors=('red','green','blue'),
                 width=1.5):
        """ add axes 

        axes : np.array(3,3)
            to turn off axes, set to None
        axes_offset : tuple
            x, y offset from top top-left atom
        
        """
        axes = np.asarray(axes)
        self._axes = [length*axes/np.linalg.norm(axes, axis=1), width,
                      offset, [str_to_colour(col) for col in colors]]

    def add_plane(self, vectors, origin=np.zeros(3), rev_normal=False, 
                  color='red', alpha=1.):
        """ add square plane to visualisation
        
       vectors : np.ndarray((2,3), dtype=float)
          The two vectors representing the edges of the plane.
       origin : np.ndarray((3,3), dtype=float), default to zero
          The origin of the plane.
       rev_normal : bool
           whether to reverse direction of normal (for lighting calculations)
       color : str
          the color of the plane, in chemlab colors
          
        """
        vectors = self._unit_conversion(np.array(vectors), 'distance')
        origin = self._unit_conversion(np.array(origin), 'distance')

        c = str_to_colour(color)
        colors = np.array([c,c,c,c,c,c])
        assert alpha <= 1. and alpha > 0., 'alpha must be between 0 and 1'
        
        n = np.cross(vectors[0], vectors[1])
        if rev_normal:
            n = -n
        n = n / np.linalg.norm(n)
        normals = np.array([n,n,n,n,n,n])
        
        vertices = np.array([origin,vectors[0]+origin,vectors[1]+origin,
                             vectors[0]+origin,vectors[0]+vectors[1]+origin,vectors[1]+origin])
        
        self._triangles.append([vertices, normals, colors, alpha])
    
    def remove_planes(self, n=1):
        """ remove the last n planes to be added """
        assert len(self._triangles) >= n
        self._triangles = self._triangles[:-n]

    def _unit_conversion(self, values, measure):
        """ 
        values : np.array 
        measure : str       
        """
        if not self._units in self._unit_dict:
            raise NotImplementedError
        if not measure in self._unit_dict[self._units]:
            raise NotImplementedError

        return values * self._unit_dict[self._units][measure]

    def _trim_image(self, im, threshold=100):
        """
        a simple solution to trim whitespace on the image
        
        1. It gets the border colour from the top left pixel, using getpixel, 
        so you don't need to pass the colour.
        2. Subtracts a scalar from the differenced image, 
        this is a quick way of saturating all values under 100, 100, 100 to zero. 
        So is a neat way to remove any 'wobble' resulting from compression.
        """
        bg = Image.new(im.mode, im.size, im.getpixel((0,0)))
        diff = ImageChops.difference(im, bg)
        diff = ImageChops.add(diff, diff, 2.0, -threshold)
        bbox = diff.getbbox()
        if bbox:
            return im.crop(bbox)
        else:
            raise RuntimeError('attempted to trim whitespace on an image that is all white')

    def _concat_images_horizontal(self, images, gap=10, background='white'):
        """ concatentate one or more PIL images horizontally 

        Parameters
        ----------
        images : PIL.Image list
            the images to concatenate
        gap : int
            the pixel gap between images
        background : PIL.ImageColor
            background color (as supported by PIL.ImageColor)
        """
        if len(images) == 1: return images[0]
        
        total_width = sum([img.size[0] for img in images]) + len(images)*gap
        max_height = max([img.size[1] for img in images])
        
        final_img = Image.new("RGBA", (total_width, max_height), color=background)
        
        horizontal_position = 0
        for img in images:
            final_img.paste(img, (horizontal_position, 0))
            horizontal_position += img.size[0] + gap
        
        return final_img

    def _concat_images_vertical(self, images, gap=10, background='white'):
        """ concatentate one or more PIL images vertically 

        Parameters
        ----------
        images : PIL.Image list
            the images to concatenate
        gap : int
            the pixel gap between images
        """
        if len(images) == 1: return images[0]
        
        total_width = max([img.size[0] for img in images]) 
        max_height = sum([img.size[1] for img in images]) + len(images)*gap
        
        final_img = Image.new("RGBA", (total_width, max_height), color=background)
        
        vertical_position = 0
        for img in images:
            final_img.paste(img, (0, vertical_position))
            vertical_position += img.size[1] + gap
        
        return final_img        
        
    def create_textline_image(self, text, fontsize=10, color=(0,0,0),background=(255,255,255),
                              boxsize=(1000,20)):
        """create a PIL image from a line of text"""
        img = Image.new('RGB',boxsize,color=background)
        d = ImageDraw.Draw(img)        
        font = ImageFont.truetype(get_data_path('Arial.ttf',module=fonts), fontsize)
        #font = ImageFont.load_default().font
        d.text((0,0),text,fill=color,font=font)
        img=self._trim_image(img)
        return img

    #TODO orthogonal perspective
    def _renderer_opengl(self, xrot=0, yrot=0, zrot=0, fov=5.,thickness=1, 
                         zoom_extents=None):
        """ render objects in opengl
        
        to open an external qtviewer use viewer.run()
        
        Parameters
        ----------
        rotx: float
            rotation about x (degrees)
        roty: float
            rotation about y (degrees)
        rotz: float
            rotation about z (degrees)
        fov : float
            field of view angle (degrees)
        thickness : float
            multiplier for thickness of lines of some objects
        zoom_extents : None or np.ndarray((N, 3))
             define an array of points to autozoom image, if None then computed automatically
        
        Return
        ------
        viewer : PyQt4.QtGui.QMainWindow   
            the qt viewing window
        widget : PyQt4.QtOpenGL.QGLWidget
            the qt widget holding the rendered objects

        """        
        # an array of all points in the image (used to calculate axes position)
        all_array = None

        # initialize graphic engine
        v = QtViewer()
        w = v.widget
        #TODO could add option to change background color, but then need inversion of other colors
        w.background_color = str_to_colour('white')
        w.initializeGL()
        w.camera.fov = fov

        ## ADD RENDERERS
        ## ----------------------------
         
        #bonds renderer
        for starts, ends, radii, colors_start, colors_end, alphas, backend, shading,linewidth in self._bonds:
            #TODO issue with bonds on top of atoms if atoms transparent and bond not
            transparent = True
            colors_start[:,3] = alphas*255
            colors_end[:,3] = alphas*255

            v.add_renderer(BondRenderer, starts, ends, colors_start, colors_end, radii, backend=backend, 
                           transparent=transparent, shading=shading,
                           linewidth=linewidth)             

            all_array = starts if all_array is None else np.concatenate([all_array,starts])
            all_array = np.concatenate([all_array,ends])

        #atoms renderer
        for r_array, radii, colors, alphas, backend, shading in self._atoms:
            
            if min(alphas) == 1:
                transparent=False
            else:
                transparent = True
            colors[:,3] = alphas*255

            v.add_renderer(AtomRenderer, r_array, radii, colors, backend=backend, 
                           transparent=transparent, shading=shading)             
       
            all_array = r_array if all_array is None else np.concatenate([all_array,r_array])
                
        #boxes render
        for box_vectors, box_origin, box_color, box_width in self._boxes:
            v.add_renderer(BoxRenderer,box_vectors,box_origin,
                           color=box_color, width=box_width*thickness)           
            #TODO account for other corners of box?
            b_array = box_vectors + box_origin                           
            all_array = b_array if all_array is None else np.concatenate([all_array,b_array])

        #hexagonal prism render
        for hex_vectors, hex_origin, hex_color, hex_width in self._hexagons:
            v.add_renderer(HexagonRenderer,hex_vectors,hex_origin,
                           color=hex_color, width=hex_width*thickness)           
            #TODO account for other vertices of hexagon?
            h_array = hex_vectors + hex_origin                           
            all_array = h_array if all_array is None else np.concatenate([all_array,h_array])

        #surfaces render
        for vertices, normals, colors, alpha in self._triangles:
            if alpha < 1.:
                transparent = True
                colors[:,3] = int(alpha*255)
            else:
                transparent = False
            v.add_renderer(TriangleRenderer,vertices, normals, colors, 
                           transparent=transparent)           
            all_array = vertices if all_array is None else np.concatenate([all_array,vertices])

        ## ----------------------------

        if all_array is None:
            # Cleanup
            w.close()
            v.clear()
            raise Exception('nothing available to render')

        # transfrom coordinate system
        w.camera.orbit_x(xrot*np.pi/180.)
        w.camera.orbit_y(yrot*np.pi/180.)
        w.camera.orbit_z(zrot*np.pi/180.)
        
        # axes renderer
        # TODO option to show a,b,c instead of x,y,z
        if self._axes is not None:
            axes, axes_width, axes_offset, axes_colors = self._axes          
            
            # find top-left coordinate after transformations and 
            # convert to original coordinate system
            
            ones = np.ones((all_array.shape[0],1))
            trans_array = np.apply_along_axis(w.camera.matrix.dot,1,np.concatenate((all_array,ones),axis=1))[:,[0,1,2]]
            t_top_left = [trans_array[:,0].min() + axes_offset[0], 
                          trans_array[:,1].max() + axes_offset[1], 
                          trans_array[:,2].min(), 1]

            x0, y0, z0 = np.linalg.inv(w.camera.matrix).dot(t_top_left)[0:3]
            origin = [x0, y0, z0]
           
            all_array = np.concatenate([all_array, [origin]])
            
            vectors = axes + origin
            for vector, color in zip(vectors, axes_colors):
                startends = [[origin, vector]]                      
                colors = [[color, color]]
                #TODO add as arrows instead of lines 
                v.add_renderer(LineRenderer, startends, colors, width=axes_width*thickness)
                #TODO add x,y,z labels (look at chemlab.graphics.__init__?)

        if zoom_extents is None:        
            w.camera.autozoom(all_array)
        else:
            w.camera.autozoom(np.asarray(zoom_extents))
        
        return v, w

    def open_qtview(self, xrot=0, yrot=0, zrot=0, fov=5.,thickness=1, 
                         zoom_extents=None):
        """ open a qt viewer of the objects
        
        Parameters
        ----------
        rotx: float
            rotation about x (degrees)
        roty: float
            rotation about y (degrees)
        rotz: float
            rotation about z (degrees)
        fov : float
            field of view angle (degrees)
        thickness : float
            multiplier for thickness of lines for some objects
        zoom_extents : None or np.ndarray((N, 3))
             define an array of points to autozoom image, if None then computed automatically
        
        Return
        ------
        viewer : PyQt4.QtGui.QMainWindow   
            the qt viewing window

        """  
        v, w = self._renderer_opengl(xrot, yrot, zrot, fov, thickness, zoom_extents)        
        v.run()
        # Cleanup
        w.close()
        v.clear()
        
        
    def get_image(self, xrot=0, yrot=0, zrot=0, fov=5., size=400, quality=5,
                  zoom_extents=None, trim_whitespace=True):
        """ get image of visualisation
        
        NB: x-axis horizontal, y-axis vertical, z-axis out of page
        
        Parameters
        ----------
        rotx: float
            rotation about x (degrees)
        roty: float
            rotation about y (degrees)
        rotz: float
            rotation about z (degrees)
        fov : float
            field of view angle (degrees)
        size : float
            size of image
        quality : float
            quality of image (pixels per point), note: higher quality will take longer to render
        zoom_extents : None or np.ndarray((N, 3))
             define an array of points to autozoom image, if None then computed automatically
        trim_whitespace : bool
            whether to trim whitspace around image
        
        Return
        ------
        image : PIL.Image

        """        
        v, w = self._renderer_opengl(xrot, yrot, zrot, fov, quality, zoom_extents)        
        
        # convert scene to image
        image = w.toimage(int(size*quality), int(size*quality))
        image.thumbnail((int(size),int(size)),Image.ANTIALIAS)
        
        if trim_whitespace:
            image = self._trim_image(image, threshold=10)

        # Cleanup
        w.close()
        v.clear()
       
        return image
        
    # TODO be able to paste one image on another, with different sizes and maintaining alpha values
        
    def visualise(self, images, columns=1, width=None, height=None): 
        """ visualise image(s) in IPython
        
        When this object is returned by an input cell or passed to the
        display function, it will result in the image being displayed
        in the frontend.
        
        Parameters
        ----------
        images : list/single PIL.Image or (x,y)
            (x,y) denotes a blank space of size x,y e.g. [img1,(100,0),img2]
        columns : int
            number of image columns 
        width : int
            Width to which to constrain the image in html
        height : int
            Height to which to constrain the image in html
        
        Returns
        -------
        image : IPython.display.Image

        """        
        try:
            img_iter = iter(images)
        except TypeError:
            img_iter = iter([images])
        
        img_columns = []
        img_rows = []
        for image in img_iter: 
            
            # add blank
            try:
                x,y = image
                image = Image.new("RGB", (x,y), "white")
            except TypeError:
                pass
                
            if len(img_columns) < columns:
                img_columns.append(image)
            else:
                img_rows.append(self._concat_images_horizontal(img_columns))
                img_columns = [image]
        if img_columns:
            img_rows.append(self._concat_images_horizontal(img_columns))
        image = self._concat_images_vertical(img_rows)
        
        b = BytesIO()
        image.save(b, format='png')
        data = b.getvalue()
        b.close() #del b
        
        return ipy_Image(data=data, width=width, height=height)

    def basic_vis(self, atoms_df=None, meta=None, 
                  spheres=True, illustrate=False, 
                  xrot=0, yrot=0, zrot=0, fov=10.,
                  axes=np.array([[1,0,0],[0,1,0],[0,0,1]]), axes_length=1., axes_offset=(-1.2,0.2),
                  size=400, quality=5):
        """ basic visualisation shortcut
        
        invoking add_atoms, add_box (if meta), add_axes, get_image and visualise functions
        
        """
        if not atoms_df is None:
            self.add_atoms(atoms_df, spheres=spheres, illustrate=illustrate)
        if not meta is None:
            self.add_box(meta.a,meta.b,meta.c,meta.origin)
        if not axes is None:
            self.add_axes(axes=axes, length=axes_length, offset=axes_offset)
            
        image = self.get_image(xrot=xrot, yrot=yrot, zrot=zrot, fov=fov, 
                               size=size, quality=quality)
        
        # cleanup
        self._atoms.pop()
        if not meta is None: self._boxes.pop()

        return self.visualise(image)
        
if __name__ == '__main__':

    import pandas as pd
    atoms_df = pd.DataFrame(
            [[2,3,4,1,[0, 0, 255],1],
             [1,3,3,1,'orange',0.5],
             [4,3,1,1,'blue',1],
    [3,4,1,1,'blue',1]],
            columns=['x','y','z','radius','color','transparency'])
    bonds_df = pd.DataFrame(
            [
             [1,2,0.1,'green','green',1],
    [0,3,0.1,'blue','green',1],
    [3,1,0.1,'red','green',1],
    [3,2,0.1,'pink','green',1]],
            columns=['start','end','radius','color_start','color_end','transparency'])
    import ipymd
    vis = ipymd.visualise_sim.Visualise_Sim()
    vis.add_atoms(atoms_df,spheres=True)
    vis.add_bonds(atoms_df,bonds_df,cylinders=True,linewidth=100)
    img1 = vis.get_image(size=400,quality=5,xrot=90,yrot=10)
    img1
    vis.open_qtview(xrot=90,yrot=10)