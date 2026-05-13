"""
Plotting the simulated TopOpt geometry with boundery conditions and loads.
This version of the code is meant for mixed element types problems. Such as
the stress intensity minimization.

Bram Lagerweij
Aerospace Structures and Materials Department TU Delft
2018
"""

import matplotlib.pyplot as plt
import matplotlib.animation as anim
import numpy as np
import os


class Plot(object):
    """
    This class contains functions that allows the visualisation of the TopOpt
    algorithem. It can print the density distribution, the boundary conditions
    and the forces.

    Parameters
    ----------
    load : object, child of the Loads class
        The loadcase(s) considerd for this optimisation problem.
    directory : str
        Relative directory that the results should be saved in.
    title : str, optional
        Title of the plot, optionaly.

    Attributes
    ---------
    nelx : int
        Number of elements in x direction.
    nely : int
        Number of elements in y direction.
    fig : matplotlib.pyplot figure
        An empty figure of size nelx/10 and nely/10 inch.
    ax : matplotlib.pyplot axis
        The axis system that belongs to fig.
    images : 1-D list with imshow objects
        This list contains all density distributions that need to be plotted.
    directory : str
        Location where the results need to be saved.
    """
    def __init__(self, load, directory, title=None):
        # create diretory if required
        if not os.path.exists(directory):
            os.makedirs(directory)
        # turning off the interactive plotting of matplotlib.pyplot
        plt.ioff()
        self.nelx = load.nelx
        self.nely = load.nely
        self.load = load
        self.fig = plt.figure()
        xsize = 100*load.nelx/1920
        ysize = 100*load.nely/1080
        schale = max(xsize, ysize)
        self.fig.set_size_inches(load.nelx/schale, load.nely/schale)
        self.ax = self.fig.add_axes([0.05, 0.05, 0.9, 0.8], frameon=False, aspect=1)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        if title is not None:
            self.fig.suptitle(title)
        self.images = []
        self.directory = directory

    def add(self, x, animated=False):
        """
        Adding a plot of the density distribution to the figure.

        Parameters
        ----------
        x : 2-D array size(nely, nelx)
            The density distribution.
        animated : bool
            An animated figure is genereted when history = True.
        """
        if animated is False:
            self.images = []
        x = x.astype(np.float32)
        plt_im = plt.imshow(x, cmap=plt.cm.gray_r, vmin=0, vmax=2, animated=animated)
        self.images.append([plt_im])

    def find(self, dof):
        """
        This function returns the location, x,y of any degree of freedom by
        corresponding it with the edof array.

        Parameters
        ----------
        dof : int
            Degree of freedom number of unknown location.

        Returns
        -------
        x : float
            x location of the dof.
        y : float
            y location of the dof.
        """
        # find first location in edofs
        # check length element
        # place at correct location in elment
        elenum = 0
        for sublist in self.load.edof:
            subnum = 0
            for item in sublist:
                if item == dof:
                    break
                subnum += 1
            if item == dof:
                break
            elenum += 1

        # element center coordinates
        elx = int(elenum/self.nely)
        ely = elenum % self.nely

        # type of element, 8 or 26 dof
        ele_len = len(self.load.edof[elenum])

        # when element is 8 dofs
        if ele_len == 8:
            xlist = [-0.5, 0.5, 0.5, -0.5]
            ylist = [0.5, 0.5, -0.5, -0.5]
            x = elx + xlist[int(subnum/2)]
            y = ely + ylist[int(subnum/2)]

        # when element has 26 dofs
        if ele_len == 26:
            xlist = [-0.5, -0.5+1/3, -0.5+2/3, 0.5, 0.5, 0.5, 0.5, 0.5-1/3, 0.5-2/3, -0.5, -0.5, -0.5, 0]
            ylist = [0.5, 0.5, 0.5, 0.5, 0.5-1/3, 0.5-2/3, -0.5, -0.5, -0.5, -0.5, -0.5+1/3, -0.5+2/3, 0]
            x = elx + xlist[int(subnum/2)]
            y = ely + ylist[int(subnum/2)]

        return x, y

    def boundary(self, load):
        """
        Plotting the boundary conditions.

        Parameters
        --------
        load : object, child of the Loads class
            The loadcase(s) considerd for this optimisation problem.
        """
        wedgepropsH = dict(arrowstyle="wedge, tail_width=1.", color='g')
        wedgepropsV = dict(arrowstyle="wedge, tail_width=1.", color='b')

        for i in load.fixdofs():
            nodex, nodey = self.find(i)
            if i % load.dim == 0:
                self.ax.annotate('', xy=(nodex, nodey), xytext=(-15, 0),
                                  textcoords='offset points', arrowprops=wedgepropsH)
            if i % load.dim == 1:
                self.ax.annotate('', xy=(nodex, nodey), xytext=(0, -15),
                                  textcoords='offset points', arrowprops=wedgepropsV)

    def loading(self, load):
        """
        Plotting the loading conditions.

        Parameters
        --------
        load : object, child of the Loads class
            The loadcase(s) considerd for this optimisation problem.
        """
        arrowprops = dict(arrowstyle="->",fc="r", ec="r", mutation_scale=20)
        forceloc = np.nonzero(load.force())[0]

        for i in forceloc:
            force = load.force()[i]
            nodex, nodey = self.find(i)
            if i % load.dim == 0:
                self.ax.annotate('', xy=(nodex, nodey), xytext=(30*force, 0),
                                 textcoords='offset points', arrowprops=arrowprops)
            if i % load.dim == 1:
                self.ax.annotate('', xy=(nodex, nodey), xytext=(0, 30*force),
                                 textcoords='offset points', arrowprops=arrowprops)

    def save(self, filename, fps=10):
        """
        Saving an plot in svg or mp4 format, depending on the length of the
        images list. The FasterFFMpegWriter is used when videos are generated.
        These videos are encoded with a hardware accelerated h264 codec with
        the .mp4 file format. Other codecs and encoders can be set within the
        function itself.

        Parameters
        ---------
        filename : str
            Name of the file, excluding the file exstension.
        fps : int
            Amount of frames per second if the plots are animations.
        """
        if len(self.images) == 1:
            self.fig.savefig(self.directory+filename+'.svg')
        else:
            writer = anim.FFMpegWriter(fps=30, codec='h264')
            animation = anim.ArtistAnimation(self.fig, self.images, interval=1, blit=True, repeat=False)
            animation.save(self.directory+filename+'.mp4', writer=writer)

    def show(self):
        """Showing the plot in a window."""
        self.fig.show()

    def saveXYZ(self, x, x_size, thickness=1):
        """
        This function allows the export of the density distribution as a point
        cloud. This can be used to create .stl files in the following steps:

        1. Open meshlab and 'import mesh' on all .xyz files.
        2. Use 'Per Vertex Normal Fnction' on all point clouds.

            * bot with [nx, ny, nz] = [ 0, 0,-1]
            * top with [nx, ny, nz] = [ 0, 0, 1]
            * x- with  [nx, ny, nz] = [-1, 0, 0]
            * x+ with  [nx, ny, nz] = [ 1, 0, 0]
            * y- with  [nx, ny, nz] = [ 0,-1, 0]
            * y+ with  [nx, ny, nz] = [ 0, 1, 0]

        3. Apply the 'Screened Poisson Surface Reconstruction' filter with the
        option of 'Merge all visible layers' as True

        Parameters
        ----------
        x : 2-D array
            Density array.
        x_size : float
            X dimension of the mesh.
        thickness : foat
            Thickness of the mesh.
        """
        thickness = thickness/2

        nely, nelx = np.shape(x)
        xx = np.linspace(0, x_size, nelx)
        yy = np.linspace(0, x_size/nelx*nely, nely)
        xyz = [[a, b] for a in xx for b in yy]

        for i in range(len(x)):
            for j in range(len(x[i])):
                index = j*len(x) + i
                xyz[index].append(x[i, j]*thickness)

        # positive face
        xyz = np.array(xyz, dtype=np.float32)

        np.savetxt(self.directory+'top.xyz', xyz)

        # negative face
        xyz[:, -1] = -1*xyz[:, -1]

        np.savetxt(self.directory+'bot.xyz', xyz)

        # side faces
        xx = np.linspace(0, x_size, nelx).tolist()
        yy = np.linspace(0, x_size/nelx*nely, nely).tolist()

        xyz = np.zeros((0, 3))
        for i in range(len(xx)):
            xi = xx[i]
            yi = 0
            thick = x[0, :][i]*thickness
            thick = np.linspace(-thick, thick, num=50)
            for t in thick:
                xyz = np.vstack((xyz, [xi, yi, t]))
        np.savetxt(self.directory+'y-.xyz', xyz)

        xyz = np.zeros((0, 3))
        for i in range(len(xx)):
            xi = xx[i]
            yi = x_size/nelx*nely
            thick = x[0, :][i]*thickness
            thick = np.linspace(-thick, thick, num=50)
            for t in thick:
                xyz = np.vstack((xyz, [xi, yi, t]))
        np.savetxt(self.directory+'y+.xyz', xyz)

        xyz = np.zeros((0, 3))
        for i in range(len(yy)):
            xi = 0
            yi = yy[i]
            thick = x[:, 0][i]*thickness
            thick = np.linspace(-thick, thick, num=50)
            for t in thick:
                xyz = np.vstack((xyz, [xi, yi, t]))
        np.savetxt(self.directory+'x-.xyz', xyz)

        xyz = np.zeros((0, 3))
        for i in range(len(yy)):
            xi = x_size
            yi = yy[i]
            thick = x[:, -1][i]*thickness
            thick = np.linspace(-thick, thick, num=50)
            for t in thick:
                xyz = np.vstack((xyz, [xi, yi, t]))
        np.savetxt(self.directory+'x+.xyz', xyz)


class FasterFFMpegWriter(anim.FFMpegWriter):
    '''FFMpeg-pipe writer bypassing figure.savefig. To improof saving speed'''

    def __init__(self, **kwargs):
        '''Initialize the Writer object and sets the default frame_format.'''
        super().__init__(**kwargs)
        self.frame_format = 'argb'

    def grab_frame(self, **savefig_kwargs):
        '''
        Grab the image information from the figure and save as a movie frame.

        Doesn't use savefig to be faster: savefig_kwargs will be ignored.
        '''
        try:
            # re-adjust the figure size and dpi in case it has been changed by
            # the user. We must ensure that every frame is the same size or
            # the movie will not save correctly.
            self.fig.set_size_inches(self._w, self._h)
            self.fig.set_dpi(self.dpi)
            # Draw and save the frame as an argb string to the pipe sink
            self.fig.canvas.draw()
            self._frame_sink().write(self.fig.canvas.tostring_argb())
        except (RuntimeError, IOError) as e:
            out, err = self._proc.communicate()
            raise IOError('Error saving animation to file (cause: {0}) '
                          'Stdout: {1} StdError: {2}. It may help to re-run '
                          'with --verbose-debug.'.format(e, out, err))
