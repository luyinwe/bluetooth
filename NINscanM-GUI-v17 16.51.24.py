
MAC_ADDR = "00:06:66:69:C6:EA"   # for NIN-M
#MAC_ADDR = "00:06:66:67:F2:D3"  # for BT development-board??
#MAC_ADDR = "00:06:66:69:c6:f0"   # for testing-board

VERBOSE       = False  # print board-related error messages?
Nsources      = 8      # number of sources per frame
SRCSIZE       = 20     # number of bytes to grab per source subframe
FRAMESIZE     = Nsources*SRCSIZE
numtimepoints = 1      # number of frames (timepoints) to grab on each try

int_yscale_max  =  65536 # for plotting int16 acquisitions (upper limit=32768)
int_yscale_min  =  0 # for plotting int16 acquisitions (lower limit=-32768)

plotinterval    = 1007    # msec; rate of _plot_timer_fired() function calls
datainterval    = 30*numtimepoints  # msec; timer firing interval, 40msec=25Hz
plotlag = 0     # lag for starting plot timer (roughly, # of frames acquired)

min_points_on_screen = 1200  # used to decide when to decimate data before plotting

outputrate = 25  # Hz; should match NIN-M output rate for Frame Lag to be useful

timings = []

#  NINdaq.py ... Version 0.150
#
# Copyright (c) 2009, Gary Strangman
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#  * Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#  * Neither the name of the Massachusetts General Hospital nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
# OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys
import glob
import time
import string
import struct
import random
import re
import wx
import numpy as np
#import bluetooth_search
from bluetooth import *
try:
    from scipy import stats
except:
    pass

from traits.etsconfig.api import ETSConfig
ETSConfig.toolkit = 'wx'
# Traits imports UI
from traits.api import *  # includes Range, Int, Bool, HasTraits, Instance
from traitsui.api import View, Item, Group, HSplit, HGroup, VGroup, VSplit, Handler, VGrid, ButtonEditor, FileEditor
from traitsui.menu import NoButtons, OKCancelButtons

# Chaco imports top
from chaco.api import create_line_plot, add_default_axes, \
                               add_default_grids, OverlayPlotContainer, \
                                 PlotLabel, VPlotContainer, \
                                 create_scatter_plot, Legend, PlotComponent
from chaco.api import Plot, AbstractPlotData, ArrayPlotData
from chaco.tools.api import PanTool, \
                                       LegendTool, TraitsTool, DragZoom
from chaco.tools.api import RangeSelection, RangeSelectionOverlay, PanTool


# Enable imports
from enable.component_editor import ComponentEditor


from traitsui.wx.editor_factory import EditorFactory
from traitsui.wx.button_editor import SimpleEditor as SimpleButtonEditor
from traitsui.wx.button_editor import CustomEditor as CustomButtonEditor
from traits.api import Str, Range, Enum, Property, Instance
from traitsui.api import View
from traitsui.ui_traits import AView, Image
# from enthought.traits.ui.wx.editor_factory import EditorFactory
# from enthought.traits.ui.wx.button_editor import SimpleEditor as SimpleButtonEditor
# from enthought.traits.ui.wx.button_editor import CustomEditor as CustomButtonEditor
# from enthought.traits.api import Str, Range, Enum, Property, Instance
# from enthought.traits.ui.api import View
# from enthought.traits.ui.ui_traits import AView, Image


# HISTORY
# v0.9 = convert to chaco v3.1 etc.

# TODO LIST
#
# make prep, samplerate, record time, input ranges READ-ONLY during run ... CLOSE
# auto-detect NI board and complain/go-on if not present
# check for boards rather than requiring command-line input? (search for @@@)
# move focus to event log automatically ... SetFocus() somewhere???
# calc recent-average numpoints per timer_tick and use that as a guide for stop_fired final-points-to-collect
# fine-tune plot y-scales in both full and normalize mode
# catch double-clicks on all buttons???


# SOME KEY GLOBAL CONSTANTS
__version__       = 0.95
plotpoints        = 2000   # max number of points to plot across screen (>=screen resolution)
#MAXrate           = 100000 # Hz; maximum sampling rate


# FIGURE OUT HOW MANY BOARDS TO RECORD FROM
if len(sys.argv)==1:
    # no board count passed; assume 1 board
    numboards = 1
else:
    numboards = string.atoi(sys.argv[1]) # string->int


# SET UP THE BOARDS WITH TYPEDEFS AND CONSTANTS (NATIONAL INSTRUMENTS NIDAQ-SPECIFIC)
prevclock = 0      # initialization
COLOR_PALETTE = np.array([(0,0,1),  # a la matlab coloring scheme
                          (0,1,0),
                          (1,0,0),
                          (0,1,1),
                          (1,1,0),
                          (1,1,0),
                          (1,0,1),
                          (0,0,0),
                          (.4,.4,.4)])

###
### DEFINE KEY CONSTANTS FOR NI DEVICE
###
#ENABLE = 0      # take this LOW to enable zCLOCK for loading data on Din for LTC1665 gain chip
#CLOCK = 1       # line for Serial Interface Clock input
#DATA = 2        # line for data input, data loaded on rising edge of clock input
#GAIN = 3        # set low for enabling gain changes
#LASERS = [5,4]  # lines for laser0/1 enabling
#CONFIG = 7      # line for configuring ninm1
#IDcounter = 1   # auto-increment this to get unique numbers for task handles

####################################################
### NOW START CREATING TRAITS-BASED GUI ELEMENTS ###
####################################################

def ToggleButtonEditor ( *args, **traits ):
    """ Allows the user to click a button; this editor is typically used with
        an event trait to fire the event.
    """
    return ToolkitEditorFactory( *args, **traits )

class ToolkitEditorFactory ( EditorFactory ):
    """ wxPython editor factory for buttons.
    """
    
    #---------------------------------------------------------------------------
    #  Trait definitions:
    #---------------------------------------------------------------------------

    # Value to set when the button is clicked
    value = Property

    # Optional label for the button
    label = Str
    enable_label = Str
    disable_label = Str

    # The name of the external object trait that the button label is synced to
    label_value = Str

    # (Optional) Image to display on the button
    image = Image
    enable_image = Image
    disable_image = Image

    # Extra padding to add to both the left and the right sides
    width_padding = Range( 0, 31, 7 )

    # Extra padding to add to both the top and the bottom sides
    height_padding = Range( 0, 31, 5 )

    # Presentation style
    style = Enum( 'button', 'radio', 'toolbar', 'checkbox' )

    # Orientation of the text relative to the image
    orientation = Enum( 'vertical', 'horizontal' )
    
    # The optional view to display when the button is clicked:
    view = AView

    #---------------------------------------------------------------------------
    #  Traits view definition:
    #---------------------------------------------------------------------------

    traits_view = View( [ 'label', 'value', '|[]' ] )

    #---------------------------------------------------------------------------
    #  Implementation of the 'value' property:
    #---------------------------------------------------------------------------

    def _get_value ( self ):
        return self._value

    def _set_value ( self, value ):
        self._value = value
        if isinstance(value, basestring):
            try:
                self._value = int( value )
            except:
                try:
                    self._value = float( value )
                except:
                    pass

    #---------------------------------------------------------------------------
    #  Initializes the object:
    #---------------------------------------------------------------------------

    def __init__ ( self, **traits ):
        self._value = 0
        super( ToolkitEditorFactory, self ).__init__( **traits )

    #---------------------------------------------------------------------------
    #  'Editor' factory methods:
    #---------------------------------------------------------------------------

    def simple_editor ( self, ui, object, name, description, parent ):
        return SimpleEditor( parent,
                             factory     = self,
                             ui          = ui,
                             object      = object,
                             name        = name,
                             description = description )

    def custom_editor ( self, ui, object, name, description, parent ):
        return CustomEditor( parent,
                             factory     = self,
                             ui          = ui,
                             object      = object,
                             name        = name,
                             description = description )

#-------------------------------------------------------------------------------
#  'SimpleEditor' class:
#-------------------------------------------------------------------------------

class SimpleEditor ( SimpleButtonEditor ):
    
    def init ( self, parent ):
        self.factory.label = self.factory.enable_label
        super(SimpleEditor, self).init(parent)
    
    def update_object ( self, event ):
        if self.factory.label == self.factory.enable_label:
            self.factory.label = self.factory.disable_label
            self.factory.value = 1
        else:
            self.factory.label = self.factory.enable_label
            self.factory.value = 0
            
        self.label = self.factory.label
        super(SimpleEditor, self).update_object(event)
        
            
class CustomEditor( CustomButtonEditor ):
    def init ( self, parent ):
        self.factory.label = self.factory.disable_label
        self.factory.image = self.factory.disable_image
        super(CustomEditor, self).init(parent)
    
    def update_object ( self, event ):
        if self.factory.label == self.factory.enable_label:
            self.factory.label = self.factory.disable_label
            self.factory.image = self.factory.disable_image
            self.factory.value = 1
        else:
            self.factory.label = self.factory.enable_label
            self.factory.image = self.factory.enable_image
            self.factory.value = 0
            
        self.label = self.factory.label
        
        #update the button
        self._control.label = self.factory.label
        self._control.image = self.factory.image
        
        super(CustomEditor, self).update_object(event)

#record which source and channel are sellected
sEnabled = [0,0,0,0,0,0,0,0]
dEnabled = [0,0,0,0,0,0,0,0]

class Source(HasTraits):
    """ninm1 Source object ... checkbox"""

    global sEnabled,dEnabled,chanEnabled,ec
    enable = Bool
    view = View( Item('enable',width=-20,height=-20,style='custom', show_label=False),
                height=0.1,
                buttons=NoButtons)

    def __init__(self,board,Snum):
        self.Snum = Snum   # source numbers are 1-8
        self.board = board
        print "Initializing Source%i, board%i" %(Snum,board)

    def _enable_changed(self):
        if self.enable:
            sEnabled[self.Snum-1] = 1
            print 'Enabling laser %i' % self.Snum            
            print "BOARD%i, LASER%i = %i" %(self.board,self.Snum-1,1)
        else:
            sEnabled[self.Snum-1] = 0
            print 'Disabling laser %i' % self.Snum
            print "BOARD%i, LASER%i = %i" %(self.board,self.Snum-1,0)


class Detector(HasTraits):
    """ninm1 Detector object ... spinner for gains +2 buttons +2 voltage-dropdowns"""
    
    global sEnabled,dEnabled,chanEnabled,ec
    enable = Bool
    
    view = View( Item('enable',width=-19,height=-20,style='custom', show_label=False),
                height=0.1,
                buttons=NoButtons)

    def __init__(self,board,Dnum):
        self.Dnum = Dnum
        self.board = board
        print "Initializing Detector%i, board%i" %(Dnum,board)


    def _enable_changed(self):
        
        if self.enable:
            dEnabled[self.Dnum-1] = 1
            print 'Enabling Detecor %i' % self.Dnum
            print "BOARD%i, Detecor%i = %i" %(self.board,self.Dnum-1,1)
        else:
            dEnabled[self.Dnum-1] = 0
            print 'Disabling Detecor %i' % self.Dnum
            print "BOARD%i, Detecor%i = %i" %(self.board,self.Dnum-1,0)


class NINM_board0(HasTraits):
    # haven't figured out how to have a class that takes arguments (board 0/1)
    board = 0
    s = []
    m=8
#    print 'ninm1 root has board',board

    #s.append(Instance(Source,(board,1)))
    s1 = Instance(Source,(board,1))
    s2 = Instance(Source,(board,2))
    s3 = Instance(Source,(board,3))
    s4 = Instance(Source,(board,4))
    s5 = Instance(Source,(board,5))
    s6 = Instance(Source,(board,6))
    s7 = Instance(Source,(board,7))
    s8 = Instance(Source,(board,8))
    
    d1 = Instance(Detector,(board,1))
    d2 = Instance(Detector,(board,2))
    d3 = Instance(Detector,(board,3))
    d4 = Instance(Detector,(board,4))
    d5 = Instance(Detector,(board,5)) 
    d6 = Instance(Detector,(board,6))
    d7 = Instance(Detector,(board,7))
    d8 = Instance(Detector,(board,8))

    SallON = Button('Plot ALL Src')
    SallOFF = Button('Plot NO Src')
    DallON = Button('Plot ALL Det')
    DallOFF = Button('Plot NO Det')

    view = View( Group(

                   HGroup( Item('s1',label='S0',style='custom',show_label=True),
                           Item('s2',label='S1',style='custom',show_label=True),
                           Item('s3',label='S2',style='custom',show_label=True),
                           Item('s4',label='S3',style='custom',show_label=True),
                           Item('s5',label='S4',style='custom',show_label=True),
                           Item('s6',label='S5',style='custom',show_label=True),
                           Item('s7',label='S6',style='custom',show_label=True),
                           Item('s8',label='S7',style='custom',show_label=True),

                           VGroup(  Item('SallON',style="custom",show_label=False,width=-74,height=-25),
                                    Item('SallOFF',style="custom",show_label=False,width=-74,height=-25),
                                 ),
                           ),
                   
                   HGroup( Item('d1',label='D0',style='custom',show_label=True),
                           Item('d2',label='D1',style='custom',show_label=True),
                           Item('d3',label='D2',style='custom',show_label=True),
                           Item('d4',label='D3',style='custom',show_label=True),
                           Item('d5',label='D4',style='custom',show_label=True),
                           Item('d6',label='D5',style='custom',show_label=True),
                           Item('d7',label='D6',style='custom',show_label=True),
                           Item('d8',label='D7',style='custom',show_label=True),
                           
                           VGroup(  Item('DallON',style="custom",show_label=False,width=-74,height=-25),
                                    Item('DallOFF',style="custom",show_label=False,width=-74,height=-25),
                                    
                                 )                          
                         ),
                       ),
                 height=0.2,
                 buttons=NoButtons
               )

    #all source on and off button
                 
    def _SallON_fired(self):
#        print "allON fired"

        self.s1.enable = True
        self.s2.enable = True
        self.s3.enable = True
        self.s4.enable = True
        self.s5.enable = True
        self.s6.enable = True
        self.s7.enable = True
        self.s8.enable = True

    def _SallOFF_fired(self):
#        print "allOFF fired"
        self.s1.enable = False
        self.s2.enable = False
        self.s3.enable = False
        self.s4.enable = False
        self.s5.enable = False
        self.s6.enable = False
        self.s7.enable = False
        self.s8.enable = False

    def _DallON_fired(self):
#        print "allOFF fired"
        self.d1.enable = True
        self.d2.enable = True
        self.d3.enable = True
        self.d4.enable = True
        self.d5.enable = True
        self.d6.enable = True
        self.d7.enable = True
        self.d8.enable = True

    def _DallOFF_fired(self):
#        print "allOFF fired"
        self.d1.enable = False
        self.d2.enable = False
        self.d3.enable = False
        self.d4.enable = False
        self.d5.enable = False
        self.d6.enable = False
        self.d7.enable = False
        self.d8.enable = False

    def set_defaults(self):
        self._DallON_fired()
        self._SallON_fired()


class TwoPlots(HasTraits):
    global numboards

    data = Instance(AbstractPlotData)
    normalize = False

    p1 = Instance(Plot)

    # set up appropriate view(s)
    view = View( Item('p1', show_label=False, editor=ComponentEditor() ),
                 width=1000,
                 height=500,
                 resizable=True)
#    print "TwoPlots numboards = ",numboards
    if numboards==2:
        plot2 = Instance(Plot)
        view = View(Group(
                          Item('p1', show_label=False, editor=ComponentEditor() ),
                          Item('p2', show_label=False, editor=ComponentEditor() ),
                         ),
                    width=1000,
                    height=600,
                    resizable=True)

    # DATA INITIALIZATION STEP   timer
    startdata1 = np.zeros((2,Nsources*8),np.int32)
    x = np.linspace(0, 1, 2)
    data = ArrayPlotData(x=x,                         #need to be extended to y0-y63
                         y0=startdata1[:,0],  y1=startdata1[:,1],  y2=startdata1[:,2],
                         y3=startdata1[:,3],  y4=startdata1[:,4],  y5=startdata1[:,5],
                         y6=startdata1[:,6],  y7=startdata1[:,7],  y8=startdata1[:,8],
                         y9=startdata1[:,9],  y10=startdata1[:,10], y11=startdata1[:,11],
                         y12=startdata1[:,12], y13=startdata1[:,13], y14=startdata1[:,14],
                         y15=startdata1[:,15], y16=startdata1[:,16], y17=startdata1[:,17],
                         y18=startdata1[:,18], y19=startdata1[:,19], y20=startdata1[:,20],
                         y21=startdata1[:,21], y22=startdata1[:,22], y23=startdata1[:,23],
                         y24=startdata1[:,24], y25=startdata1[:,25], y26=startdata1[:,26],
                         y27=startdata1[:,27], y28=startdata1[:,28], y29=startdata1[:,29],
                         y30=startdata1[:,30], y31=startdata1[:,31], y32=startdata1[:,32],
                         y33=startdata1[:,33], y34=startdata1[:,34], y35=startdata1[:,35],
                         y36=startdata1[:,36], y37=startdata1[:,37], y38=startdata1[:,38],
                         y39=startdata1[:,39], y40=startdata1[:,40], y41=startdata1[:,41],
                         y42=startdata1[:,42], y43=startdata1[:,43], y44=startdata1[:,44],
                         y45=startdata1[:,45], y46=startdata1[:,46], y47=startdata1[:,47],
                         y48=startdata1[:,48], y49=startdata1[:,49], y50=startdata1[:,50],
                         y51=startdata1[:,51], y52=startdata1[:,52], y53=startdata1[:,53],
                         y54=startdata1[:,54], y55=startdata1[:,55], y56=startdata1[:,56],
                         y57=startdata1[:,57], y58=startdata1[:,58], y59=startdata1[:,59],
                         y60=startdata1[:,60], y61=startdata1[:,61], y62=startdata1[:,62],
                         y63=startdata1[:,63])
                         

    # PLOT CREATION STEP
    p1 = Plot(data)

    plotchan = ['x','y0','y1','y2','y3','y4','y5','y6','y7','y8','y9','y10','y11','y12','y13','y14','y15','y16','y17',
                'y18','y19','y20','y21','y22','y23','y24','y25','y26','y27','y28','y29','y30','y31','y32','y33','y34','y35',
                'y36','y37','y38','y39','y40','y41','y42','y43','y44','y45','y46','y47','y48','y49','y50','y51','y52','y53',
                'y54','y55','y56','y57','y58','y59','y60','y61','y62','y63']
    p1.plot(plotchan,color_mapper=COLOR_PALETTE)
    p1.padding_top = 5
    p1.padding_bottom = 6  # hide xlabel
    p1.padding_left = 40
    p1.padding_right = 5

    # color_mapper doesn't work so ...           need to be extended to y0-y63
    p1.plots['plot0'][0].color = 'blue'
    p1.plots['plot0'][1].color = 'green'
    p1.plots['plot0'][2].color = 'red'
    p1.plots['plot0'][3].color = 'cyan'
    p1.plots['plot0'][4].color = 'magenta'
    p1.plots['plot0'][5].color = 'yellow'
    p1.plots['plot0'][6].color = 'black'
    p1.plots['plot0'][7].color = 'brown'
    p1.plots['plot0'][8].color = 'blue'
    p1.plots['plot0'][9].color = 'green'
    p1.plots['plot0'][10].color = 'red'
    p1.plots['plot0'][11].color = 'cyan'
    p1.plots['plot0'][12].color = 'magenta'
    p1.plots['plot0'][13].color = 'yellow'
    p1.plots['plot0'][14].color = 'black'
    p1.plots['plot0'][15].color = 'brown'
    p1.plots['plot0'][16].color = 'blue'
    p1.plots['plot0'][17].color = 'green'
    p1.plots['plot0'][18].color = 'red'
    p1.plots['plot0'][19].color = 'cyan'
    p1.plots['plot0'][20].color = 'magenta'
    p1.plots['plot0'][21].color = 'yellow'
    p1.plots['plot0'][22].color = 'black'
    p1.plots['plot0'][23].color = 'brown'
    p1.plots['plot0'][24].color = 'blue'
    p1.plots['plot0'][25].color = 'green'
    p1.plots['plot0'][26].color = 'red'
    p1.plots['plot0'][27].color = 'cyan'
    p1.plots['plot0'][28].color = 'magenta'
    p1.plots['plot0'][29].color = 'yellow'
    p1.plots['plot0'][30].color = 'black'
    p1.plots['plot0'][31].color = 'brown'
    p1.plots['plot0'][32].color = 'blue'
    p1.plots['plot0'][33].color = 'green'
    p1.plots['plot0'][34].color = 'red'
    p1.plots['plot0'][35].color = 'cyan'
    p1.plots['plot0'][36].color = 'magenta'
    p1.plots['plot0'][37].color = 'yellow'
    p1.plots['plot0'][38].color = 'black'
    p1.plots['plot0'][39].color = 'brown'
    p1.plots['plot0'][40].color = 'blue'
    p1.plots['plot0'][41].color = 'green'
    p1.plots['plot0'][42].color = 'red'
    p1.plots['plot0'][43].color = 'cyan'
    p1.plots['plot0'][44].color = 'magenta'
    p1.plots['plot0'][45].color = 'yellow'
    p1.plots['plot0'][46].color = 'black'
    p1.plots['plot0'][47].color = 'brown'
    p1.plots['plot0'][48].color = 'blue'
    p1.plots['plot0'][49].color = 'green'
    p1.plots['plot0'][50].color = 'red'
    p1.plots['plot0'][51].color = 'cyan'
    p1.plots['plot0'][52].color = 'magenta'
    p1.plots['plot0'][53].color = 'yellow'
    p1.plots['plot0'][54].color = 'black'
    p1.plots['plot0'][55].color = 'brown'
    p1.plots['plot0'][56].color = 'blue'
    p1.plots['plot0'][57].color = 'green'
    p1.plots['plot0'][58].color = 'red'
    p1.plots['plot0'][59].color = 'cyan'
    p1.plots['plot0'][60].color = 'magenta'
    p1.plots['plot0'][61].color = 'yellow'
    p1.plots['plot0'][62].color = 'black'
    p1.plots['plot0'][63].color = 'brown'
 
    if normalize:
        p1.value_range.set_bounds(0,1)
    else:
        p1.value_range.set_bounds(int_yscale_min,int_yscale_max)
#    p1.tools.append(PanTool(p1))
#    p1.overlays.append(SimpleZoom(p1))

class Controller(TwoPlots):
    global numboards,sEnbaled,dEnabled,plotinterval,datainterval
    duration = Int(4000)
    samplerate = Int(outputrate)
    runtimestr = String("Frame Count: 0")
    realtimestr = String("Real Time: 0")
    prep = Button(label='Prep')
    start = Button(label='Start')  # disabled to start
    stop = Button(label='Stop')

    clear = Button(label='Clear')
    
    normalize = Button(label='Normalize')
    norm = False
    output = Button(label='ASCII')
    stripchart = Int(4)  # sec
    events = String("")

    block = ''  # initialize Bluetooth data block to empty

    curcount = 0  # when not using board-data

    parent = None
    ready_for_start = Bool(True)
    taking_data = Bool(False)
    datatimer = None
    plottimer = None
    starttime = None

    outname = None
    outputtype = 'ascii'  # DEFAULT; determines how data is saved
    ext = '.dat'          # DEFAULT; use .bdat for binary outputs, .dat for ascii ones
    i = 0

    skip_this_plot = False
    framelag = None

    socket = None

    sleeptime = 0.001
    plots = Instance(TwoPlots,())

    # max number of data points to accumulate and show in the plot
    max_num_points = Int(stripchart.default_value*samplerate.default_value)

    # CREATE AND INITIALIZE NINM
    ninm1 = Instance(NINM_board0,())

    # CREATE GUI LAYOUT
    view = View( Item('plots',style='custom', show_label=False),
                 HGroup (
                   # put 2 NIRS instruments on the left (one above the other)
                   VGroup( Item('ninm1', label='ninm1', style='custom', show_label=True),
                         ),
                   # put program controls on the right
                   VGroup(
                     HGroup( Item('duration',style='simple',label='Recording Time (s):',width=-60,height=-22,show_label=True),
####                             Item('samplerate',style='simple',label='Sample Rate (Hz):',width=-60,height=-22,show_label=True),
                             Item('stripchart',style='simple',width=-60,height=-22,dock='vertical',label='Strip Time (s)',show_label=True),
                             Item('runtimestr',style='readonly',width=-160,height=-22,show_label=False),
                             Item('realtimestr',style='readonly',width=-160,height=-22,show_label=False),
                           ),
                     HGroup( #Item('prep',style='custom',width=-110,height=-40,show_label=False,enabled_when='taking_data=False'),
                             Item('start',style='custom',width=-110,height=-40,show_label=False,enabled_when='ready_for_start==True'),
                             Item('stop',style='custom',width=-110,height=-40,show_label=False,enabled_when='taking_data==True'),
                             Item('normalize',
                                   editor=ToggleButtonEditor(style='button',
                                                             disable_label='To Normalized',
                                                             enable_label='    To Raw'),
                                   style='custom',width=-110,height=-40,show_label=False),
                             Item('clear',style='custom',width=-110,height=-40,show_label=False,enabled_when='taking_data==False'),
                             Item('output',
                                   editor=ToggleButtonEditor(style='button',
                                                             disable_label='ASCII',
                                                             enable_label='Binary'),
                                   style='custom',width=-70,height=-40,show_label=True),
                           ),  # close second controls HGroup
                     Item('events',style='simple',label='Event log:',width=50,height=-22,show_label=True),
                         )  # close controls VGroup
                        ), # close entire bottom-panel (non-plots) HGroup
               width = 0.9,
               height = 0.9,
               resizable = True,
               buttons = NoButtons)

    def _ninm1_changed(self):
#        print "ninm1_changed"
        pass

    def multiple_replace(text,adict):
        rx = re.compile('|'.join(map(re.escape,adict)))
        def one_xlat(match):
            return adict[match.group(0)]
        return rx.sub(one_xlat,text)

        
    def _prep_fired(self):
#        print "prep_fired"
        self.ninm1.set_defaults()

        self.runtimestr = " Frame Count: 0"  # clear this out for a new run
        self.realtimestr = "  Real Time: 0"
        self.plots.normalize = self.norm

        try:
            self.socket = BluetoothSocket( RFCOMM )
            self.socket.bind(('',0))
            self.socket.connect((MAC_ADDR, 1))
            time.sleep(0.05)
            self.socket.settimeout(0)  #@@@0 is "nonblocking"
            print "CONNECTED ..."
        except:
            print "\nNO SOCKET!!! Trying to continue anyway ...\n"
            self.socket = None
        

        # DIALOG TO GET A FILENAME FOR SAVING
        skipsave = False  # for folk
###        outname = OutFile()
###        outname.configure_traits()
###        if outname.outname == '':
        self.outname = 'junk'  # default for skipping the save

        # SEE IF FILENAME ALREADY EXISTS; IF SO, APPEND _1, _2, _3 ETC.
        counter = 1
        newname = self.outname*1
        while len(glob.glob(newname+'.dat')+glob.glob(newname+'.bdat')):  # while there's a match
            newname = self.outname +'_'+str(counter)
            counter += 1
        self.outname = newname
        print "OUTPUT FILENAME: ",newname

        # PREP FOR STARTING
        self.title = self.outname
        self.ready_for_start = True

        # clear out any existing data or screen plot              need to be extented
        zonk = np.zeros((1),np.int32)
        self.plots.data.set_data('x',zonk)
        for i in range(Nsources*8):
            self.plots.data.set_data('y'+str(i),zonk)

        # PRE-ALLOCATE MEMORY FOR RECORDING = DURATION*SAMPLERATE
        self.x = np.linspace(0,self.duration,self.duration*self.samplerate)
        
        self.alldata = np.zeros((Nsources*8,self.duration*self.samplerate),np.int32)
        self.datapointer = 0
        self.events = ''

        self.needmore = 0
        
    def _start_fired(self):
#        print "start_fired"
        if self.taking_data:
            print "bailed to avoid re-spawn"
            return  # prevent re-spawning background process (and associated crash)
        else:
            # FIRST TIME HERE, MAKE SURE YOU PREP FIRST
            self.taking_data = True

            # IF HAVEN'T STARTED, DO PREP OPERATIONS FIRST
            self.ninm1.set_defaults()

            self.runtimestr = " Frame Count: 0"  # clear this out for a new run
            self.realtimestr = "  Real Time: 0"
            self.plots.normalize = self.norm

            try:
                self.socket = BluetoothSocket( RFCOMM )
                self.socket.bind(('',0))
                self.socket.connect((MAC_ADDR, 1))
                time.sleep(0.05)
                self.socket.settimeout(0)  #@@@0 is "nonblocking"
                print "CONNECTED ..."
            except:
                print "\nNO SOCKET!!! Trying to continue anyway ...\n"
                self.socket = None


            # DIALOG TO GET A FILENAME FOR SAVING
            skipsave = False  # for folk
    ###        outname = OutFile()
    ###        outname.configure_traits()
    ###        if outname.outname == '':
            self.outname = 'junk'  # default for skipping the save

            # SEE IF FILENAME ALREADY EXISTS; IF SO, APPEND _1, _2, _3 ETC.
            counter = 1
            newname = self.outname*1
            while len(glob.glob(newname+'.dat')+glob.glob(newname+'.bdat')):  # while there's a match
                newname = self.outname +'_'+str(counter)
                counter += 1
            self.outname = newname
            print "OUTPUT FILENAME: ",newname

            # PREP FOR STARTING
            self.title = self.outname
            self.ready_for_start = True

            # clear out any existing data or screen plot              need to be extented
            zonk = np.zeros((1),np.int32)
            self.plots.data.set_data('x',zonk)
            for i in range(Nsources*8):
                self.plots.data.set_data('y'+str(i),zonk)

            # PRE-ALLOCATE MEMORY FOR RECORDING = DURATION*SAMPLERATE
            self.x = np.linspace(0,self.duration,self.duration*self.samplerate)

            self.alldata = np.zeros((Nsources*8,self.duration*self.samplerate),np.int32)
            self.datapointer = 0
            self.events = ''

            self.needmore = 0
            # END PREP TASKS

        # START COLLECTING
        # Start up the timers!  We have to tell it how many milliseconds
        # to wait between timer events. Pause between them to avoid(??) lockups.
        self.firethegun = time.clock()  # set clock to 0
        self.datatimer.Start(datainterval, wx.TIMER_CONTINUOUS)
        if self.datatimer.IsRunning():
            print "********* STARTED DATA TIMER *********"
        else:
            print "!!!!!!!!! DID **NOT** START DATA TIMER !!!!!!!!!!!!!!!!"
        self.starttime = time.time()
        time.sleep(datainterval/1000.*plotlag)  # wait before starting plotter ##datainterval/1000.*0.3)  # convert to msec, shift by percentage
        self.plottimer.Start(plotinterval, wx.TIMER_CONTINUOUS)
        print "+++++++++ STARTED PLOT TIMER +++++++++"

    def _stop_fired(self):
#        print "stop_fired"
        #numremaining = self.alldata.shape[1]-self.datapointer

        numtimepoints = 1
        samp = self.getFrames(numtimepoints)    
        samp = samp.reshape((Nsources*8,numtimepoints))

#        print "END:", self.datapointer, samp
#        self.alldata[:-1, self.datapointer:self.datapointer+samp] = self.bufferdata[:samp*Nsources*8].reshape((Nsources*8,samp))
        self.alldata[:,self.datapointer:self.datapointer+numtimepoints] = samp
        self.datapointer += numtimepoints

        self.taking_data = False
        self.curcount = 0   # reset the whereami counter (in case it wasn't)
        self.datatimer.Stop()
        self.plottimer.Stop()
        stoptimestr = time.asctime()

        # DISCONNECT AND REQUIRE ANOTHER PREP
        if self.socket:
            self.socket.close()
            self.socket = None
#        self.ready_for_start = False  ## this forces another prep
        self.starttime = None
        self.datapointer = 0


    def getFrames(self, Nframes):
        """Uses getBytes to receive raw (string) data and returns int32 data for the
        requested number of frames."""

        tic = time.clock()
#        print "entered getFrames"
        # RETURN DOUBLE-RAMP DATA IF NO SOCKET CONNECTION
        if self.socket==None:
            fact = random.random()
            time.sleep(0.012+fact*(0.020))  # sleep for 10-30msec
            allints = []
            for i in range(Nframes):
                ints = (np.arange(Nsources*8)*((self.datapointer+i)%outputrate))*10*(((self.datapointer+i)/outputrate)%4+1)  # ramp every 25 points (1 sec)
                allints += list(ints)
            toc = time.clock()
            timings.append(toc-tic)
#            print "fabricated data ...", len(allints), self.datapointer, time.clock(), round(self.datapointer-(tic-self.firethegun)*outputrate), 
#            if 'stats' in globals():
#                print stats.mean(timings)
#            else:
#                print
            return np.array(allints)

        # IF THERE *IS* A SOCKET ...
        # GET AT LEAST Nframes WORTH OF BYTES (STARTING AT THE BEGINNING OF A SRC0 INDEX)
        idx = self.block.find('SRC0')
        while len(self.block[idx:])<FRAMESIZE*Nframes:
######            print "Before getBytes",len(self.block),
            self.block += self.getBytes(FRAMESIZE)
            idx = self.block.find('SRC0')
######            print " ... After getBytes",len(self.block)

###        print "parsing data"
        # PARSE DATA ASSUMING NO MISSING PACKETS/DATAPOINTS
        Realdata = ''
        for i in range(Nframes):
            for j in range(Nsources):
                Realdata += self.block[(j*SRCSIZE)+(idx+4):(j*SRCSIZE)+idx+20]
####            Realdata += self.block[idx+4:idx+20]+self.block[idx+24:idx+40]+self.block[idx+44:idx+60]+self.block[idx+64:idx+80]+self.block[idx+84:idx+100]+self.block[idx+104:idx+120]+self.block[idx+124:idx+140]+self.block[idx+144:idx+160]
            self.block = self.block[idx+FRAMESIZE:]  # truncate to extra

        newdata = struct.unpack('>'+'HHHHHHHH'*Nsources*Nframes, Realdata)
        toc = time.clock()
        timings.append(toc-tic)
#        print "got data ...", len(newdata), self.datapointer, time.clock(), round(self.datapointer-(tic-self.firethegun)*outputrate), 
#        if 'stats' in globals():
#            print stats.mean(timings)
#        else:
#            print
        return np.array(newdata)

    def getBytes(self, n_bytes):
        """ Receives and returns the given number of bytes. Tries to handle
        any issues that may arise. """

        bytes = ''
        while len(bytes)<n_bytes:
            bytes += self.socket.recv(1)  #####n_bytes)
        return bytes

    def _normalize_fired(self):
#        print 'normalize_fired'
        if self.norm == False:
            self.norm = True
        else:
            self.norm = False

    def _clear_fired(self):
        self.ninm1.s1.enable = False
        self.ninm1.s2.enable = False
        self.ninm1.s3.enable = False
        self.ninm1.s4.enable = False
        self.ninm1.s5.enable = False
        self.ninm1.s6.enable = False
        self.ninm1.s7.enable = False
        self.ninm1.s8.enable = False
        self.ninm1.d1.enable = False
        self.ninm1.d2.enable = False
        self.ninm1.d3.enable = False
        self.ninm1.d4.enable = False
        self.ninm1.d5.enable = False
        self.ninm1.d6.enable = False
        self.ninm1.d7.enable = False
        self.ninm1.d8.enable = False

        # ZERO OUT THE PLOT
        zonk = np.zeros((1),np.int32)
        self.plots.data.set_data('x',zonk)
        #self.socket.close()

        for i in range(Nsources*8):
            self.plots.data.set_data('y'+str(i),zonk)

    def _stripchart_changed(self):
        print "stripchart_changed"
        self.max_num_points = self.stripchart*self.samplerate

    def _events_changed(self,event):
        if self.taking_data:
            self.alldata[-1,self.datapointer] = ord(event[-1])


    def data_timer_tick(self, event):
        """ Callback function that should get called based on a wx timer
        tick.  This will generate a new random datapoint and set it on
        the .data array of our viewer object.
        """
        if self.taking_data == True:
            # Get new data and increment the tick count
#            print "Getting DATA. self.datapointer=",self.datapointer, time.clock()

            # SAMPLING DATA
            samp = self.getFrames(numtimepoints)
#            print FRAMESIZE, numtimepoints, len(samp)

#            print "samp before reshape: %s" %samp
            samp = samp.reshape((numtimepoints,Nsources*8))
#            print "samp now: %s" %samp

            # STORE THIS BATCH OF SAMPLES IN THE MAIN DATA FRAME, AND MOVE POINTER
            self.alldata[:, self.datapointer:self.datapointer+numtimepoints] = samp.T
            self.datapointer += numtimepoints
        return


    def plot_timer_tick(self, event):
        """ Callback function that should get called based on a wx timer
        tick.  This will generate a new random datapoint and set it on
        the .data array of our viewer object.
        """
        global prevclock

        #runtime = np.floor(self.datapointer/float(self.samplerate))
        runtime = self.datapointer/float(datainterval)
        realruntime = time.clock()
        
        if (realruntime)<(self.duration):
            tic = time.clock()
            newframelag = round(self.datapointer-(tic-self.firethegun)*outputrate)
            self.runtimestr = " Frame Lag: %i" %newframelag
#            print "Frame lags:",self.framelag, newframelag
            if self.framelag is None:
                self.framelag = newframelag
            elif newframelag < self.framelag-1:
                self.skip_this_plot = True
            self.framelag = newframelag
        else:
            self._stop_fired()

        if self.skip_this_plot==True:
            self.skip_this_plot = False
            print "SKIPPING THIS PLOT-CALL:", self.framelag, newframelag
            return

        self.realtimestr = " Real Time: %.1f" %(round(realruntime,1))

        if self.taking_data == True:
            # PLOT DATA
            idxmin = max(0, self.datapointer-self.stripchart*self.samplerate)
            points_in_window = (self.datapointer-idxmin)
            decimate_factor = max(1,points_in_window/min_points_on_screen)

            print "PLOTTING. self.datapointer=",self.datapointer, idxmin, self.alldata.shape, self.datapointer/float(realruntime)

#            print"datapointer=%d" %self.datapointer
#            print "est. time: %f" %runtime
#            print "real time :%f" %realruntime
            
            # FIND AN "OPTIMAL" DECIMATION FACTOR
#            while 1:
#                if (points_in_window/decimate_factor)>plotpoints:
#                    decimate_factor += 1  # integer math, for easy downsampling
#                    continue
#                else:
#                    break

            x = self.x[idxmin:self.datapointer:decimate_factor]
            y = self.alldata[:, idxmin:self.datapointer:decimate_factor].T
            self.plots.data.set_data('x',x)

#            print self.datapointer, samp, "cycletime:",runtime-prevclock, decimate_factor, idxmin, points_in_window
            prevclock = runtime

            # CALCULATE WHICH CHANNEL IS SELECTED
            chanEnabled = np.outer(sEnabled,dEnabled)
            ec = np.ravel(chanEnabled)
            
            m = 0
            if self.norm==False:  # minimize ifs, which means normalizing code is lower down
                # set yranges
                self.plots.p1.value_range.set_bounds(int_yscale_min,int_yscale_max)

                # set visible/not individual channels
                for m in range(len(ec)):
                    if ec[m]==1:
                        self.plots.data.set_data('y'+str(m),y[:,m])
                        self.plots.p1.plots['plot0'][m].visible = True
                    else:
                        self.plots.p1.plots['plot0'][m].visible = False
                        
            elif self.norm==True:
                # set yranges
                self.plots.p1.value_range.set_bounds(0,1)

                # change data if plot is requested; otherwise turn plot invisible
                mins = np.min(y,0)
                maxs = np.max(y,0)
                diffs = maxs-mins

                for m in range(len(ec)):
                    if ec[m]==1:
                        self.plots.data.set_data('y'+str(m),(y[:,m]-mins[m])/float(diffs[m]))
                        self.plots.p1.plots['plot0'][m].visible = True
                    else:
                        self.plots.p1.plots['plot0'][m].visible = False

        #self.sleeptime = 0.001
        #time.sleep(self.sleeptime)
        return

    def keypress(self, event):
        """ Callback function that should get called when a key is pressed on controls.
        Store key code in last column of data array based on datapointer. Not real
        accurate, but not bad.
        """
        crash
        self.alldata[-1, self.datapointer] = event.GetKeyCode()


class OutFile(HasTraits):
    outname = File()

    fview = View( Item('outname',label='Save File Name:',style='simple',editor=FileEditor()),
                  title='Save File Name',
                  kind='modal',
                  width = -400,
                  height = -300,
                  buttons = OKCancelButtons)

class MyMenu( wx.PySimpleApp ):  
    def __init__(self,parent,ID,title):
        wx.Frame.__init__(self,parent,-1,title,wx.DefaultPosition,wx.Size(200, 150))
        menubar=wx.MenuBar()  
        file=wx.Menu()  
        edit=wx.Menu()  
        help=wx.Menu()  
        file.Append(101,'&Open','Open a new document')  
        file.Append(102,'&Save','Save the document')  
        file.AppendSeparator()  
        quit=wx.MenuItem(file,105,'&Quit\tCtrl+Q','Quit the Application')  
        quit.SetBitmap(wx.Image('stock_exit-16.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap())  
        file.AppendItem(quit)  
        menubar.Append(file,'&File')  
        menubar.Append(edit,'&Edit')  
        menubar.Append(help,'&Help')  
        self.SetMenuBar( menubar )


#class MyApp(wx.PySimpleApp):
class MyApp(wx.App):
    def OnInit(self, *args, **kw):
        controls = Controller() #parent=self, plots=plots)
        view = View( Item('controls',style='custom'),
                   width = -1400,
                   height = -800,
                   buttons = NoButtons)
        controls.numboards = numboards

        self.controls = controls

        # CREATE THE TIMER FOR DATA COLLECTION/PLOT TICKS
        self.setup_timers(controls)

        # BUILD THE GUI
        controls.configure_traits()

        frame=MyMenu(None,-1,'menu1.py')
        return True

#    def _on_close(event):
#        controls.datatimer.Stop()
#        controls.plottimer.Stop()
#        controls.Destroy()
   
    def setup_buttons(self):
        pass
   
    def setup_timers(self, controls):
        # CREATE A TIMER FOR PLOTTING
        controls.plottimerId = wx.NewId()
        controls.plottimer = wx.Timer(self, controls.plottimerId)
        self.Bind(wx.EVT_TIMER, controls.plot_timer_tick, id=controls.plottimerId)

        # CREATE A TIMER FOR DATA COLLECTION
        controls.datatimerId = wx.NewId()
        controls.datatimer = wx.Timer(self, controls.datatimerId)
        self.Bind(wx.EVT_TIMER, controls.data_timer_tick, id=controls.datatimerId)

#        self.Bind(wx.EVT_CLOSE, self._on_close, id=controls.datatimerId)

        return


if __name__ == "__main__":
    # start up the GUI
    app = MyApp()
    app.MainLoop()
