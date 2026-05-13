"""
Plotting the simulated TopOpt geometry with boundery conditions and loads.

Bram Lagerweij
Aerospace Structures and Materials Department TU Delft
2018
"""

import matplotlib.pyplot as plt
import matplotlib.animation as anim
import numpy as np


class Plot(object):
    """
    This class contains functions that allows the visualisation of the TopOpt
    algorithem. It can print the density distribution, the boundary conditions
    and the forces.

    Parameters
    ----------
    load : object, child of the Loads class
        The loadcase(s) considerd for this optimisation problem.
    title : str, optional
        Title of the plot if required.

    Attributes
    ---------
    nelx : int
        Number of elements in x direction.
    nely : int
        Number of elements in y direction.
    fig : matplotlib.pyplot figure
        An empty figure of size nelx/10 and nely/10*1.2 inch.
    ax : matplotlib.pyplot axis
        The axis system that belongs to fig.
    images : 1-D list with imshow objects
        This list contains all density distributions that need to be plotted.
    """
    def __init__(self, load, title=None):
        # turning off the interactive plotting of matplotlib.pyplot
        plt.ioff()
        self.nelx = load.nelx
        self.nely = load.nely
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

    def add(self, x, animated=False):
        """
        Adding a plot of the density distribution to the figure.

        Parameters
        ----------
        x : 2-D array size(nely, nelx)
            The density distribution.
        animated : bool, optional
            An animated figure is genereted when history = True.
        """
        if animated is False:
            self.images = []
        x = x.astype(np.float32)
        plt_im = plt.imshow(1-x, vmin=0, vmax=1, cmap=plt.cm.gray, animated=animated)
        self.images.append([plt_im])

    def boundary(self, load):
        """
        Plotting the boundary conditions.

        Parameters
        ----------
        load : object, child of the Loads class
            The loadcase(s) considerd for this optimisation problem.
        """
        wedgepropsH = dict(arrowstyle="wedge, tail_width=1.", color='g')
        wedgepropsV = dict(arrowstyle="wedge, tail_width=1.", color='b')

        for i in load.fixdofs():
            if i % load.dim == 0:
                node = int((i)/load.dim)
                nodex = int(node/(self.nely + 1))-0.5
                nodey = node % (self.nely + 1)-0.5

                self.ax.annotate('', xy=(nodex, nodey), xytext=(-15, 0),
                                  textcoords='offset points', arrowprops=wedgepropsH)

            if i % load.dim == 1:
                node = int((i)/load.dim)
                nodex = int(node/(self.nely + 1))-0.5
                nodey = node % (self.nely + 1)-0.5

                self.ax.annotate('', xy=(nodex, nodey), xytext=(0, -15),
                                  textcoords='offset points', arrowprops=wedgepropsV)

    def loading(self, load):
        """
        Plotting the loading conditions.

        Parameters
        ----------
        load : object, child of the Loads class
            The loadcase(s) considerd for this optimisation problem.
        """
        arrowprops = dict(arrowstyle="simple",fc="r", ec="r", mutation_scale=20)

        forceloc = np.nonzero(load.force())[0]

        for i in forceloc:
            force = load.force()[i]

            if i % load.dim == 0:
                node = int((i)/load.dim)
                nodex = int(node/(self.nely + 1))-0.5
                nodey = node % (self.nely + 1)-0.5

                self.ax.annotate('', xy=(nodex, nodey), xytext=(-60*force, 0),
                                  textcoords='offset points', arrowprops=arrowprops)

            if i % load.dim == 1:
                node = int((i)/load.dim)
                nodex = int(node/(self.nely + 1))-0.5
                nodey = node % (self.nely + 1)-0.5

                self.ax.annotate('', xy=(nodex, nodey), xytext=(0, -60*force),
                                  textcoords='offset points', arrowprops=arrowprops)

    def save(self, filename, fps=10):
        """
        Saving an plot in svg or mp4 format, depending on the length of the
        images list. The FasterFFMpegWriter is used when videos are generated.
        These videos are encoded with a hardware accelerated h264 codec with
        the .mp4 file format. Other codecs and encoders can be set within the
        function itself.

        Parameters
        ----------
        filename : str
            Name of the file, excluding the file exstension.
        fps : int, optional
            Amount of frames per second if the plots are animations.
        """
        if len(self.images) == 1:
            print("ii")
            self.fig.savefig(filename+'.svg')
        else:
            writer = anim.FFMpegWriter(fps=30, codec='h264')
            animation = anim.ArtistAnimation(self.fig, self.images, interval=1, blit=True, repeat=False)
            animation.save(filename+'.mp4', writer=writer)

    def show(self):
        """
        Showing the plot in a window.
        """
        self.fig.show()


class FasterFFMpegWriter(anim.FFMpegWriter):
    '''FFMpeg-pipe writer bypassing figure.savefig. To improofs speed with
    respect to the matplotlib.animation.FFMpegWriter'''

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