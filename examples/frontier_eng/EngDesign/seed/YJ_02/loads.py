"""
This file containts the Load class that allows the generation of an object that
contains geometric, mesh, loads and boundary conditions that belong to the
load case. This version of the code is meant for global compliance minimization.

Bram Lagerweij
Aerospace Structures and Materials Department TU Delft
2018
"""

import numpy as np


class Load(object):
    """
    Load parent class that contains the basic functions used in all load cases.
    This class and its children do cantain information about the load case
    conciderd in the optimisation. The load case consists of the mesh, the
    loads, and the boundaries conditions. The class is constructed such that
    new load cases can be generated simply by adding a child and changing the
    function related to the geometry, loads and boundaries.

    Parameters
    ----------
    nelx : int
        Number of elements in x direction.
    nely : int
        Number of elements in y direction.
    young : float
        Youngs modulus of the materias.
    Emin : float
        Artifical Youngs modulus of the material to ensure a stable FEA.
        It is used in the SIMP based material model.
    poisson : float
        Poisson ration of the material.

    Attributes
    ----------
    nelx : int
        Number of elements in x direction.
    nely : int
        Number of elements in y direction.
    young : float
        Youngs modulus of the materias.
    Emin : float
        Artifical Youngs modulus of the material to ensure a stable FEA.
        It is used in the SIMP based material model.
    poisson : float
        Poisson ration of the material.
    dim : int
        Amount of dimensions conciderd in the problem, set at 2.
    """
    def __init__(self, nelx, nely, young, Emin, poisson):
        self.nelx = nelx
        self.nely = nely
        self.young = young
        self.Emin = Emin
        self.poisson = poisson
        self.dim = 2

    # compute 1D index from 2D position for node (boundary of element)
    def node(self, elx, ely):
        """
        Calculates the topleft node number of the requested element

        Parameters
        ---------
        elx : int
            X position of the conciderd element.
        ely : int
            Y position of the conciderd element.

        Returns
        -------
        topleft : int
            The node number of the top left node
        """
        return (self.nely+1)*elx + ely

    # compute the 4 boundary nodes of an element
    def nodes(self, elx, ely):
        """
        Calculates all node numbers of the requested element

        Parameters
        ---------
        elx : int
            X position of the conciderd element.
        ely : int
            Y position of the conciderd element.

        Returns
        -------
        n1 : int
            The node number of the top left node.
        n2 : int
            The node number of the top right node.
        n3 : int
            The node number of the bottom right node.
        n4 : int
            The node number of the bottom left node.
        """
        n1 = self.node(elx,     ely    )
        n2 = self.node(elx + 1, ely,   )
        n3 = self.node(elx + 1, ely + 1)
        n4 = self.node(elx,     ely + 1)
        return n1, n2, n3, n4

    # edof that returns an array
    def edof(self):
        """
        Generates an array with the position of the nodes of each element in
        the global stiffness matrix.

        Returns
        -------
        edof : 2-D array size(nelx*nely, 8)
            The list with all elements and their degree of freedom numbers.
        x_list : 1-D array len(nelx*nely*8*8)
            The list with the x indices of all ellements to be inserted into
            the global stiffniss matrix.
        y_list : 1-D array len(nelx*nely*8*8)
            The list with the y indices of all ellements to be inserted into
            the global stiffniss matrix.
        """
        # Creating list with element numbers
        elx = np.repeat(range(self.nelx), self.nely).reshape((self.nelx*self.nely, 1))  # x position of element
        ely = np.tile(range(self.nely), self.nelx).reshape((self.nelx*self.nely, 1))  # y position of element

        n1, n2, n3, n4 = self.nodes(elx, ely)
        edof = np.array([self.dim*n1,self.dim*n1+1, self.dim*n2,self.dim*n2+1,
                         self.dim*n3,self.dim*n3+1, self.dim*n4,self.dim*n4+1])
        edof = edof.T[0]

        x_list = np.repeat(edof, 8)  # flat list pointer of each node in an element
        y_list = np.tile(edof, 8).flatten()  # flat list pointer of each node in element
        return edof, x_list, y_list

    # element (local) stiffness matrix
    def lk(self, E, nu):
        """
        Calculates the local siffness matrix depending on E and nu.

        Parameters
        ----------
        E : float
            Youngs modulus of the material.
        nu : float
            Poisson ratio of the material.

        Returns
        -------
        ke : 2-D array size(8, 8)
            Local stiffness matrix.
        """
        k = np.array([1/2-nu/6,1/8+nu/8,-1/4-nu/12,-1/8+3*nu/8,-1/4+nu/12,-1/8-nu/8,nu/6,1/8-3*nu/8])
        ke = E/(1-nu**2) * \
            np.array([[k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
                      [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
                      [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
                      [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
                      [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
                      [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
                      [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
                      [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]]])
        return ke

    def force(self):
        """
        Returns an 1D array, the force vector of the loading condition.

        Returns
        -------
        f : 1-D array length covering all degrees of freedom
            Empy force vector.
        """
        return np.zeros(self.dim*(self.nely+1)*(self.nelx+1))

    def alldofs(self):
        """
        Returns a list with all degrees of freedom.

        Returns
        -------
        all : 1-D list
            List with numbers from 0 to the maximum degree of freedom number.
        """
        return [x for x in range(self.dim*(self.nely+1)*(self.nelx+1))]

    def fixdofs(self):
        """
        Returns a list with indices that are fixed by the boundary conditions.

        Returns
        -------
        fix : 1-D list
            List with all the numbers of fixed degrees of freedom. This list is
            empty in this parrent class.
        """
        return []

    def freedofs(self):
        """
        Returns a list of arr indices that are not fixed

        Returns
        -------
        free : 1-D list
            List containing all elemens of alldogs except those that appear in
            the freedofs list.
        """
        return list(set(self.alldofs()) - set(self.fixdofs()))

    def passive(self):
        """
        Retuns three lists containing the location and magnitude of fixed
        density values

        Returns
        -------
        elx : 1-D list
            X coordinates of all passive elements, empty for the parrent class.
        ely : 1-D list
            Y ccordinates of all passive elements, empty for the parrent class.
        values : 1-D list
            Density values of all passive elements, empty for the parrent class.
        fix_ele : 1-D list
            List with all element numbers that are allowed to change.
        """
        return [], [], [], [x for x in range(self.nelx*self.nely)]

# example loading scenario, half mbb-beam (symetry around y axis)
class HalfBeam(Load):
    """
    This child of the Loads class represents the loading conditions of a half
    mbb-beam. Only half of the beam is considerd due to the symetry around the
    y axis.

    No methods are added compared to the parrent class. The force and fixdofs
    functions are changed to output the correct force vector and boundary
    condition used in this specific load case. See the functions themselfs
    for more details
    """
    def __init__(self, nelx, nely, young, Emin, poisson):
        super().__init__(nelx, nely, young, Emin, poisson)

    def force(self):
        """
        The force vector containts a load in negative y direction at the top
        left corner.

        Returns
        -------
        f : 1-D array length covering all degrees of freedom
            A -1 is placed at the index of the y direction of the top left node.
        """
        f = super().force()
        f[1] = -1.0
        return f

    def fixdofs(self):
        """
        The boundary conditions of the half mbb-beam fix the x displacments of
        all the nodes at the outer left side and the y displacement of the
        bottom right element.

        Returns
        -------
        fix : 1-D list
            List with all the numbers of fixed degrees of freedom.
        """
        n1, n2, n3, n4 = self.nodes(self.nelx-1, self.nely-1)
        return ([x for x in range(0, self.dim*(self.nely+1), self.dim)] + [self.dim*n3+1])


# example loading scenario, mbb-beam without use of symetry axis
class Beam(Load):
    """
    This child of the Loads class represents the full mbb-beam without assuming
    an axis of symetry. To enforce an node in the middle nelx needs to be an
    even number.

    No methods are added compared to the parrent class. The force and fixdofs
    functions are changed to output the correct force vector and boundary
    condition used in this specific load case. See the functions themselfs
    for more details
    """
    def __init__(self, nelx, nely, young, Emin, poisson):
        super().__init__(nelx, nely, young, Emin, poisson)
        if nelx % 2 != 0:
            raise ValueError('nelx needs to be even in a mbb beam')

    def force(self):
        """
        The force vector containts a load in negative y direction at the mid
        top node.

        Returns
        -------
        f : 1-D array length covering all degrees of freedom
            Where at the inndex relating to the y direction of the top mid node
            a -1 is placed.
        """
        f = super().force()
        n1, n2, n3, n4 = self.nodes(int(self.nelx/2), 0)
        f[self.dim*n1+1] = -1.0
        return f

    def fixdofs(self):
        """
        The boundary conditions of the full mbb-beam fix the x  and y
        displacment of the bottom left node ande the y displacement of the
        bottom right node.

        Returns
        -------
        fix : 1-D list
            List with all the numbers of fixed degrees of freedom.
        """
        n11, n12, n13, n14 = self.nodes(0, self.nely-1)
        n21, n22, n23, n24 = self.nodes(self.nelx-1, self.nely-1)
        return ([self.dim*n14, self.dim*n14+1, self.dim*n23+1])


# cantilever beam load in the middle of the end
class Canti(Load):
    """
    This child of the Loads class represents the loading conditions of a
    cantilever beam. The beam is encasted on the left an the load is applied at
    the middel of the right side. To do this an even number for nely is
    required.

    No methods are added compared to the parrent class. The force and fixdofs
    functions are changed to output the correct force vector and boundary
    condition used in this specific load case. See the functions themselfs
    for more details
    """
    def __init__(self, nelx, nely, young, Emin, poisson):
        super().__init__(nelx, nely, young, Emin, poisson)
        if nely % 2 != 0:
            raise ValueError('nely needs to be even in a cantilever beam')

    def force(self):
        """
        The force vector containts a load in negative y direction at the mid
        most rigth node.

        Returns
        -------
        f : 1-D array length covering all degrees of freedom
            Where at the inndex relating to the y direction of the mid right
            node a -1 is placed.
        """
        f = super().force()
        n1, n2, n3, n4 = self.nodes(self.nelx-1, int(self.nely/2))
        f[self.dim*n2+1] = -1
        return f

    def fixdofs(self):
        """
        The boundary conditions of the cantileverbeam fix the x and y
        displacment of all nodes on the left side.

        Returns
        -------
        fix : 1-D list
            List with all the numbers of fixed degrees of freedom.
        """
        return ([x for x in range(0, self.dim*(self.nely+1))])


# the Michell structures wich analytical salutions (symetry arround y axsi)
class Michell(Load):
    """
    This child of the Loads class represents the loading conditions of a
    half a Michell structure. A load is applied in the mid left of the design
    space and the boundary conditions fixes the x and y direction of the
    middle right node. Due to symetry all nodes at the left side are constraint
    in x direction. This class requires nely to be even.

    No methods are added compared to the parrent class. The force and fixdofs
    functions are changed to output the correct force vector and boundary
    condition used in this specific load case. See the functions themselfs
    for more details
    """
    def __init__(self, nelx, nely, young, Emin, poisson):
        super().__init__(nelx, nely, young, Emin, poisson)
        if nely % 2 != 0:
            raise ValueError('nely needs to be even in a michell strucure')

    def force(self):
        """
        The force vector containts a load in negative y direction at the mid
        most left node.

        Returns
        -------
        f : 1-D array length covering all degrees of freedom
            Where at the inndex relating to the y direction of the mid left
            node a -1 is placed.
        """
        f = super().force()
        n1, n2, n3, n4 = self.nodes(0, int(self.nely/2))
        f[self.dim*n2+1] = -1
        return f

    def fixdofs(self):
        """
        The boundary conditions of the half mbb-beam fix the x displacments of
        all the nodes at the outer left side and the y displacement of the
        mid right element.

        Returns
        -------
        fix : 1-D list
            List with all the numbers of fixed degrees of freedom.
        """
        n1, n2, n3, n4 = self.nodes(self.nelx-1, int(self.nely/2))
        return ([self.dim*n2+1]+[x for x in range(0, self.dim*(self.nely+1), self.dim)])


# the biaxcal tension example
class BiAxial(Load):
    """
    This child of the Loads class represents the loading conditions of a
    bi-axial loaded plate. All outer nodes have a load applied that goes
    outward. This class is made to show the checkerboard problem that generaly
    occeurs with topology optimisation.

    No methods are added compared to the parrent class. The force, fixdofs and
    passive functions are changed to output the correct force vector, boundary
    condition and passive elements used in this specific load case.
    See the functions themselfs for more details
    """
    def __init__(self, nelx, nely, young, Emin, poisson):
        super().__init__(nelx, nely, young, Emin, poisson)

    def force(self):
        """
        The force vector containing loads that act outward from the edge.

        Returns
        -------
        f : 1-D array length covering all degrees of freedom
            Where at the indices related to the outside nodes an outward force
            of 1 is inserted.
        """
        f = super().force()
        # uprard force at the top side and half load in corner
        loc_up = np.arange(1, self.dim*(self.nelx+1)*(self.nely+1), self.dim*(self.nely+1))
        f[loc_up] = -1
        # right force at the right hand side
        loc_right = np.arange(self.dim*(self.nely+1)*self.nelx, self.dim*(self.nely+1)*(self.nelx+1), self.dim)
        f[loc_right] = -1
        # bottom force down
        loc_down = np.arange(self.dim*(self.nely+1)-1, self.dim*(self.nely+1)*(self.nelx+1), self.dim*(self.nely+1))
        f[loc_down] = 1
        # left force left
        loc_left = np.arange(0, self.dim*(self.nely+1), self.dim)
        f[loc_left] = 1
        return f

    def fixdofs(self):
        """
        The boundary conditions fix the top left node in x direction, the
        bottom left node in x and y direction and the bottom right node in y
        direction only.

        Returns
        -------
        fix : 1-D list
            List with all the numbers of fixed degrees of freedom.
        """
        return  [0, self.dim*(self.nely), self.dim*(self.nely)+1, self.dim*(self.nelx+1)*(self.nely+1)-1]

    def passive(self):
        """
        The Bi-Axial load case requires fully dense elements around the border.
        This is done to enforce propper load introduction.

        Returns
        -------
        elx : 1-D list
            X coordinates of all passive elements, empty for the parrent class.
        ely : 1-D list
            Y ccordinates of all passive elements, empty for the parrent class.
        values : 1-D list
            Density values of all passive elements, empty for the parrent class.
        """
        elx = 2*[x for x in range(self.nelx)] + [0 for y in range(self.nely)] \
                + [self.nelx-1 for y in range(self.nely)] + [0+1, self.nelx-2, 0+1, self.nelx-2]
        ely = [0 for x in range(self.nelx)] + [self.nely-1 for x in range(self.nelx)] \
                + 2*[y for y in range(self.nely)] + [0+1, 0+1, self.nely-2, self.nely-2]
        values = np.ones((len(elx)))
        return elx, ely, values
