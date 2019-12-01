
MAC_ADDR = "00:06:66:69:C6:EA"   # for NIN-M
#MAC_ADDR = "00:06:66:69:c6:f0"   # for testing-board

VERBOSE       = False  # print board-related error messages?
Nsources      = 1      # number of sources per frame
SRCSIZE       = 20     # number of bytes to grab per source subframe
FRAMESIZE     = Nsources*SRCSIZE
numtimepoints = 1      # number of frames (timepoints) to grab on each try

int_yscale_max  =  65538 # for plotting int16 acquisitions (upper limit=32768)
int_yscale_min  =  -1 # for plotting int16 acquisitions (lower limit=-32768)

plotinterval    = 30    # msec; rate of _plot_timer_fired() function calls
datainterval    = 30*numtimepoints  # msec; timer firing interval, 40msec=25Hz
plotlag = 0     # lag for starting plot timer (roughly, # of frames acquired)

min_points_on_screen = 1200  # used to decide when to decimate data before plotting

outputrate = 25  # Hz; should match NIN-M output rate for Frame Lag to be useful

timings = []

import sys
import glob
import time
import string
import struct
import serial
import random
import re
import wx
import numpy as np
from scipy import signal
#import bluetooth_search
from bluetooth import *
try:
    from scipy import stats
except:
    pass

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
sEnabled = [0,0,0,0,0,0,1,1,1]
dEnabled = [0,0,0,0,0,0,0,0]
defaultEnabled = True

class Source(HasTraits):
    """ninm1 Source object ... checkbox"""

    global sEnabled,dEnabled,chanEnabled,ec,defaultEnabled
    enable = Bool
    view = View( Item('enable',width=-20,height=-20,style='custom', show_label=False),
                height=0.1,
                buttons=NoButtons)

    def __init__(self,board,Snum,default):
        self.Snum = Snum   # source numbers are 1-8
        self.board = board
        self.enable=default
        print "Initializing Source%i, board%i" %(Snum,board)

    def _enable_changed(self):
        global defaultEnabled
        if self.enable:
            sEnabled[self.Snum-1] = 1
            print 'Enabling laser %i' % self.Snum
            defaultEnabled = False
#            print "BOARD%i, LASER%i = %i" %(self.board,self.Snum-1,1)
        else:
            sEnabled[self.Snum-1] = 0
            print 'Disabling laser %i' % self.Snum
            defaultEnabled = False
#            print "BOARD%i, LASER%i = %i" %(self.board,self.Snum-1,0)


class Detector(HasTraits):
    """ninm1 Detector object ... spinner for gains +2 buttons +2 voltage-dropdowns"""

    global sEnabled,dEnabled,chanEnabled,ec,defaultEnabled
    enable = Bool

    view = View( Item('enable',width=-19,height=-20,style='custom', show_label=False),
                height=0.1,
                buttons=NoButtons)

    def __init__(self,board,Dnum):
        self.Dnum = Dnum
        self.board = board
        self.enable=True
        print "Initializing Detector%i, board%i" %(Dnum,board)


    def _enable_changed(self):
        global defaultEnabled
        if self.enable:
            dEnabled[self.Dnum-1] = 1
            print 'Enabling Detecor %i' % self.Dnum
            defaultEnabled = False
#            print "BOARD%i, Detecor%i = %i" %(self.board,self.Dnum-1,1)
        else:
            dEnabled[self.Dnum-1] = 0
            print 'Disabling Detecor %i' % self.Dnum
            defaultEnabled = False
#            print "BOARD%i, Detecor%i = %i" %(self.board,self.Dnum-1,0)


class NINM_board0(HasTraits):
    # haven't figured out how to have a class that takes arguments (board 0/1)
    board = 0
    s = []
    m=8
#    print 'ninm1 root has board',board

    #s.append(Instance(Source,(board,1)))
    s1 = Instance(Source,(board,1,False))
    s2 = Instance(Source,(board,2,False))
    s3 = Instance(Source,(board,3,False))
    s4 = Instance(Source,(board,4,False))
    s5 = Instance(Source,(board,5,False))
    s6 = Instance(Source,(board,6,False))
    s7 = Instance(Source,(board,7,True))
    s8 = Instance(Source,(board,8,True))
    s9 = Instance(Source,(board,9,True))



    SallON = Button('Plot ALL Src')
    SallOFF = Button('Plot NO Src')

    
    view = View( VGroup(

                   HGroup( Item('s1',label='S0',style='custom',show_label=True),
                           Item('s2',label='S1',style='custom',show_label=True),
                           Item('s3',label='S2',style='custom',show_label=True),
                           Item('s4',label='S3',style='custom',show_label=True),
                           Item('s5',label='S4',style='custom',show_label=True),
                           Item('s6',label='S5',style='custom',show_label=True),
                           Item('s7',label='S6',style='custom',show_label=True),
                           Item('s8',label='S7',style='custom',show_label=True),
                           Item('s9',label='S8',style='custom',show_label=True),
                           ),
                           ),
                 height=0.4,
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
        defaultEnabled = False

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
        defaultEnabled = False


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
    startdata1 = np.zeros((2,Nsources*16),np.int32)
    x = np.linspace(0, 1, 2)
    data = ArrayPlotData(x=x,                         #need to be extended to y0-y63
                         y0=startdata1[:,0],  y1=startdata1[:,1],  y2=startdata1[:,2],
                         y3=startdata1[:,3],  y4=startdata1[:,4],  y5=startdata1[:,5],
                         y6=startdata1[:,6],  y7=startdata1[:,7],  y8=startdata1[:,8],
                         y9=startdata1[:,9],  y10=startdata1[:,10])

    # PLOT CREATION STEP
    p1 = Plot(data)

    plotchan = ['x','y0','y1','y2','y3','y4','y5','y6','y7','y8','y9','y10']
    p1.plot(plotchan)#,color_mapper=COLOR_PALETTE)
    p1.padding_top = 5
    p1.padding_bottom = 6  # hide xlabel
    p1.padding_left = 40
    p1.padding_right = 5

    # color_mapper doesn't work so ...           need to be extended to y0-y63
    p1.plots['plot0'][0].color = 'blue'
    p1.plots['plot0'][1].color = 'green'
    p1.plots['plot0'][2].color = 'red'
    p1.plots['plot0'][3].color = 'black'
    p1.plots['plot0'][4].color = 'magenta'
    p1.plots['plot0'][5].color = 'black'
    p1.plots['plot0'][6].color = 'black'
    p1.plots['plot0'][7].color = 'brown'
    p1.plots['plot0'][8].color = 'blue'
    p1.plots['plot0'][9].color = 'green'
    p1.plots['plot0'][10].color = 'red'
    

    p1.value_range.set_bounds(-1000,17000000)
#    p1.tools.append(PanTool(p1))
#    p1.overlays.append(SimpleZoom(p1))

class Controller(TwoPlots):
    global numboards,sEnbaled,dEnabled,plotinterval,datainterval,defaultEnabled
    duration = Int(4000)
    samplerate = Int(outputrate)
    runtimestr = String("Frame Count: 0")
    realtimestr = String("Real Time: 0")
    prep = Button(label='Prep')
    start = Button(label='Start')  # disabled to start
    stop = Button(label='Stop')
    sys=Int(140)
    dia=Int(80)
    calibrate=Button(label='Calibrate STA')

    baseline = Button(label='Baseline')

    normalize = Button(label='Normalize')
    norm = False
    output = Button(label='ASCII')
    autoscale=Button(label="AutoScale")
    stripchart = Int(4)  # sec
    events = String("")
    filterResult=Bool(True)
    realResult=Bool(False)
    BPResult=Bool(False)


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
    baselinenum=12000
    k=0
    b=0
    startpoint=0
    UpperBound=13000
    LowerBound=-2000
    UpperBoundLarger = Button('UpperBound+')
    UpperBoundSmaller= Button('UpperBound-')
    LowerBoundLarger= Button('LowerBound+')
    LowerBoundSmaller=Button('LowerBound-')
    syst=Int(140, label="Sys", desc="Systolic BP")
    diab=Int(80,label="Dia",desc="Diabolic BP")

    # max number of data points to accumulate and show in the plot
    max_num_points = Int(stripchart.default_value*samplerate.default_value)

    # CREATE AND INITIALIZE NINM
    ninm1 = Instance(NINM_board0,())

    # CREATE GUI LAYOUT
    view = View( Item('plots',style='custom', show_label=False),
                 HGroup (
                   # put 2 NIRS instruments on the left (one above the other)
                   VGroup( Item('ninm1', label='ninm1', style='custom', show_label=False),
                        HGroup(
                            Item('UpperBoundLarger',style="custom",show_label=False,width=-94,height=-25),
                            Item('UpperBoundSmaller',style="custom",show_label=False,width=-94,height=-25),
                            Item('LowerBoundLarger',style="custom",show_label=False,width=-94,height=-25),
                            Item('LowerBoundSmaller',style="custom",show_label=False,width=-94,height=-25)
                            )
                         ),

                   # put program controls on the right
                   VGroup(
                     HGroup( 
                            Item('sys',style='simple',label='Systolic',width=-45,height=-17,show_label=True),
                            Item('dia',style='simple',label='Diabolic',width=-45,height=-17,show_label=True),
                            Item('calibrate',style='custom',show_label=False),
                            Item('filterResult',style="custom",show_label=True,label="FiltR"),
                            Item("realResult",label="RealResult",style="custom",show_label=True),
                            Item('BPResult',label="BP",style="custom",show_label=True)
                           ),
                     HGroup( #Item('prep',style='custom',width=-110,height=-40,show_label=False,enabled_when='taking_data=False'),
                             Item('start',style='custom',width=-110,height=-40,show_label=False,enabled_when='ready_for_start==True'),
                             Item('stop',style='custom',editor=ToggleButtonEditor(style='button',
                                                             disable_label='Pause',
                                                             enable_label='Continue'),
                                    width=-110,height=-40,show_label=False,enabled_when='taking_data==True'),
                             Item('normalize',
                                   editor=ToggleButtonEditor(style='button',
                                                             disable_label='To Normalized',
                                                             enable_label='    To Raw'),
                                   style='custom',width=-110,height=-40,show_label=False),
                             Item('baseline',style='custom',width=-110,height=-40,show_label=False),
                             Item('autoscale',style='custom',width=-110,height=-40,show_label=False)
                           ),  # close second controls HGroup
                         ),
                      VGroup(Item("syst",label="Sys",style='readonly',emphasized=True),
                             Item("diab",label="Dia",style='readonly',emphasized=True)
                          )  # close controls VGroup
                        ), # close entire bottom-panel (non-plots) HGroup
               width = 0.9,
               height = 0.9,
               resizable = True,
               buttons = NoButtons)
    def __init__(self):
        self.data=""
        self.data_all=np.array([[0],[0],[0],[0],[0],[0],[0],[0],[0]])
        self.afterFilter=[]
        self.realData=[]
        self.BPWave=[]
        self.running=False


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
        self.connection=BlutoothFunction()

        try:
            self.connection.Connect()
            time.sleep(0.5)
        
        except:
            print "\nNO SOCKET!!! \n"
          

        # DIALOG TO GET A FILENAME FOR SAVING
        skipsave = False
###      
        self.outname = 'junk'  # default for skipping the save

        # SEE IF FILENAME ALREADY EXISTS; IF SO, APPEND _1, _2, _3 ETC.
        counter = 1
        newname = self.outname*1
        while len(glob.glob(newname+'.dat')+glob.glob(newname+'.bdat')):  # while there's a match
            newname = self.outname +'_'+str(counter)
            counter += 1
        self.outname = newname
#        print "OUTPUT FILENAME: ",newname

        # PREP FOR STARTING
        self.title = self.outname
        self.ready_for_start = True

        # clear out any existing data or screen plot              need to be extented
        zonk = np.zeros((1),np.int32)
        self.plots.data.set_data('x',zonk)
        for i in range(Nsources*8+3):
            self.plots.data.set_data('y'+str(i),zonk)

        # PRE-ALLOCATE MEMORY FOR RECORDING = DURATION*SAMPLERATE
        self.x = np.linspace(0,self.duration,self.duration*self.samplerate)
        self.alldata = np.zeros((Nsources*8,self.duration*self.samplerate),np.int32)
        self.datapointer = 0
        self.events = ''

        self.needmore = 0
    def _UpperBoundLarger_fired(self):
        self.UpperBound+=1000
        self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)

    def _UpperBoundSmaller_fired(self):
        if self.LowerBound+1000<self.UpperBound:
            self.UpperBound-=1000
        self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)

    def _LowerBoundLarger_fired(self):
        if self.LowerBound+1000<self.UpperBound:
            self.LowerBound+=1000
        self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)

    def _LowerBoundSmaller_fired(self):
        self.LowerBound-=1000
        self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)

    def _autoscale_fired(self):
        self.autoScale()

    def _start_fired(self):
       
        if self.taking_data:
#          
            return  # prevent re-spawning background process (and associated crash)
        else:
            # FIRST TIME HERE, MAKE SURE YOU PREP FIRST
            self.taking_data = True
            self.running=True
            # IF HAVEN'T STARTED, DO PREP OPERATIONS FIRST
            self.ninm1.set_defaults()

            # CALL _prep_fired()
            self._prep_fired()
            # END PREP TASKS
            time.sleep(0.5)
            wx.CallLater(10,self.collectData)
            wx.CallLater(20,self.processData)
        # START COLLECTING
        # Start up the timers!  We have to tell it how many milliseconds
        # to wait between timer events. Pause between them to avoid(??) lockups.
        self.firethegun = time.clock()  # set clock to 0
        self.starttime = time.time()
        self.plottimer.Start(plotinterval, wx.TIMER_CONTINUOUS)
        print "+++++++++ STARTED PLOT TIMER +++++++++"

    def _stop_fired(self):
        if self.running:
            self.running=False
        else:
            self.running=True
    
    def processData(self):
        index=self.data.find('::')
        while index != -1:
            self.data=self.data[index+2:]
            temp=self.data.find('::')
            if temp==36:
                data_processed=struct.unpack('>LLLLLLLLL',self.data[:36])
               # print data_processed[8]
                self.data_all=np.column_stack((self.data_all,np.array(data_processed)))
                self.BPWave.append(0)
                self.realData.append(0)
                self.afterFilter.append(0)
              # self.data_all[4,-1]=self.baselinenum-self.data_all[7,-1]
            index=self.data.find('::')
        wx.CallLater(10,self.processData)
        length=len(self.data_all[6])
        if length>100000:
            self.data_all=self.data_all[:,length-3000:length-1]
            self.BPWave=self.BPWave[length-3000:length-1]
            self.afterFilter=self.afterFilter[length-3000:length-1]
            self.realData=self.realData[length-3000:length-1]
            length=len(self.data_all[6])
        if length>1002:
            self.afterFilter[length-1001:length-1]=self.low_pass_filter(self.data_all[7,length-1001:length-1])
            for i in range(length-1001,length-1):
                self.realData[i]=self.baselinenum-self.afterFilter[i]
                self.BPWave[i]=int(self.k*self.realData[i]+self.b)
     
    def collectData(self):
        char=self.connection.Collect_data()
        self.data+=char
        wx.CallLater(10,self.collectData)

    def _normalize_fired(self):
#        print 'normalize_fired'
        if self.norm == False:
            self.norm = True
            self.LowerBound=0
            self.UpperBound=200
            self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)
        else:
            self.norm = False
            self.LowerBound=-1000
            self.UpperBound=13000
            self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)

    def _baseline_fired(self):
        #self.baselinenum=0
        length=len(self.data_all[6])
        self.baselinenum=int(np.mean(self.afterFilter[length-1001:length-1]))
        print "baseline= ",self.baselinenum

    def _stripchart_changed(self):
        print "Stripchart range changed"
        self.max_num_points = self.stripchart*self.samplerate

    def _events_changed(self,event):
        if self.taking_data:
            self.alldata[-1,self.datapointer] = ord(event[-1])

    def _calibrate_fired(self,event):
        peak=[]
        valley=[]
        length=len(self.data_all[4])
        peak,valley=self.find_peakvalley(self.data_all[4,length-2001:length-1])
        print "peak= ",peak
        print "valley= ",valley
        n1=np.mean(peak)
        n2=np.mean(valley)
        print self.sys,"(sys)"
        print self.dia,"(dia)"
        self.k=float(self.sys-self.dia)/float(n1-n2)
        self.b=self.sys-self.k*n1
        print 'k= ',self.k,',b= ',self.b
        wx.CallLater(100,self.calculateBP)
        
    def find_peakvalley(self,data):
        peak=[]
        valley=[]
        hs=20
        vs=[min(data),max(data)]
        peakNumber=1
        valleyNumber=1
        i=hs+1
        while (i<len(data)-hs):
            top=i-hs
            bottom=i+hs
            tempT=0
            tempB=0
            for j in range(top,bottom+1):
                if data[j]>=data[i]:
                    tempT+=1
                if data[j]<=data[i]:
                    tempB+=1
            if tempT==1:
                peak.append(data[i])
            if tempB==1:
                valley.append(data[i])
            i+=1
        return peak,valley


    def find_peaks(self,data):
        thres_min,thres_max,maxdata,mindata=self.find_threshold(data)
        print thres_max,' ',thres_min,' ',maxdata,' ',mindata
        print data
        maxpoints=[0]
        self.peaks=[]
        self.valleys=[]
        minpoints=[0]
        for i in range(len(data)-1):
            if (data[i]<=thres_max)and (data[i+1]>=thres_max) or (data[i]>=thres_max)and (data[i+1]<=thres_max):
                print data[i]
                maxpoints.append(i)
            if data[i]==thres_min:
                minpoints.append(i)
        print 'maxpoint= ',maxpoints
        for i in range(len(maxpoints)-1):
            temp=max(data[maxpoints[i]:maxpoints[i+1]])
            if temp>thres_max+200:
                self.peaks.append(temp)
                print np.argmax(data[maxpoints[i]:maxpoints[i+1]])+maxpoints[i]
        for i in range(len(minpoints)-1):
            temp=min(data[minpoints[i]:minpoints[i+1]])
            if temp<thres_min-100:
                self.valleys.append(temp)
        print self.peaks
        print self.valleys
        

    def find_threshold(self,data):
        maxdata=max(data)      
        mindata=min(data)
        return int(0.3*maxdata+0.7*mindata),int(0.7*maxdata+0.3*mindata),maxdata,mindata

    def low_pass_filter(self,data):
        b,a = signal.butter(3,0.08,'low')
        new_data=signal.filtfilt(b,a,data)
        return new_data

    def plot_timer_tick(self, event):
        """ Callback function that should get called based on a wx timer
        tick.  This will generate a new random datapoint and set it on
        the .data array of our viewer object.
        """
        global prevclock,sEnabled
        self.plots.data.set_data('x',np.linspace(1,1000,1000))
        if defaultEnabled:
            ec = np.array([0,0,0,0,0,0,1,1])
        else:
            #    chanEnabled = np.outer(sEnabled,dEnabled)
            #    ec = np.ravel(chanEnabled)
            ec=np.array(sEnabled)

        m = 0
        if (self.running and len(self.data_all[0])>1000):  # minimize ifs, which means normalizing code is lower down
                # set yranges
                # set visible/not individual channels
            length=len(self.data_all[0])
            print length
            for m in range(len(ec)):
                length=len(self.data_all[m])                
                if ec[m]==1:
                    self.plots.data.set_data('y'+str(m),self.data_all[m,length-1001:length-1])
                    self.plots.p1.plots['plot0'][m].visible = True
                else:
                    self.plots.p1.plots['plot0'][m].visible = False
            if self.realResult:
                self.plots.data.set_data('y9',self.realData[length-1001:length-1])
                self.plots.p1.plots['plot0'][9].visible=True
            else:
                self.plots.p1.plots['plot0'][9].visible=False

            if self.BPResult:
                self.plots.data.set_data('y10',self.BPWave[length-1001:length-1])
                self.plots.p1.plots['plot0'][10].visible=True
            else:
                self.plots.p1.plots['plot0'][10].visible=False
        return
    def keypress(self, event):
        """ Callback function that should get called when a key is pressed on controls.
        Store key code in last column of data array based on datapointer. Not real
        accurate, but not bad.
        """
        crash
        self.alldata[-1, self.datapointer] = event.GetKeyCode()

    def calculateBP(self):
        """Calculate BP From current data"""
        length=len(self.data_all[3])
        peaks,valleys=self.find_peakvalley(self.data_all[3,length-2001:length-1])
        print peaks
        if (len(peaks)>0):
            sys=int(np.average(peaks))
            self.syst=sys
            print "sys= ",sys
        if (len(valleys)>0):
            dia=int(np.average(valleys))
            self.diab=dia
            print "dia= ",dia
        wx.CallLater(1000,self.calculateBP)

    def autoScale(self):
        global prevclock,sEnabled
        ec=np.array(sEnabled)
        #print sum(ec)+self.realResult+self.BPResult+self.filterResult
        if ((sum(ec)+self.realResult+self.BPResult+self.filterResult)==1):

            for i in range(8):
                if (ec[i]==1):
                    length=len(self.data_all[i])
                    minimum=min(self.data_all[i,length-1001:length-1])
                    maximum=max(self.data_all[i,length-1001:length-1])
                    if minimum>0:
                        self.LowerBound=int(minimum)-50
                    else:
                        self.LowerBound=int(minimum)-50
                    if maximum>0:
                        self.UpperBound=int(maximum)+50
                    else:
                        self.UpperBound=int(maximum)+50
                    self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)
            if self.realResult==1:
                length=len(self.realData)
                minimum=min(self.realData[length-1000:length-1])
                maximum=max(self.realData[length-1000:length-1])
                self.LowerBound=int(minimum)-50
                self.UpperBound=int(maximum)+50
                self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)

            if self.BPResult==1:
                length=len(self.BPWave)
                minimum=min(self.BPWave[length-1000:length-1])
                maximum=max(self.BPWave[length-1000:length-1])
                self.LowerBound=int(minimum)-50
                self.UpperBound=int(maximum)+50
                self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)

            if self.filterResult==1:
                length=len(self.afterFilter)
                minimum=min(self.afterFilter[length-1000:length-1])
                maximum=max(self.afterFilter[length-1000:length-1])
                self.LowerBound=int(minimum)-50
                self.UpperBound=int(maximum)+50
                self.plots.p1.value_range.set_bounds(self.LowerBound,self.UpperBound)


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

class BlutoothFunction:
    def __init__(self):
        
        self.data10086=''
        

    def Connect(self):
        self.connection=serial.Serial("COM4",baudrate=19200)
        print "Connected~"
        time.sleep(1)

    def Collect_data(self):
        #print 'Collecting~'
        char=""   
        num_waiting=self.connection.inWaiting()
        if (num_waiting):
        # print time.time()
            char=self.connection.read(num_waiting)
        return char

    def Stop(self):
        self.timer.Stop()



class MyApp(wx.PySimpleApp):
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

        return


if __name__ == "__main__":
    # start up the GUI
    app = MyApp()
    app.MainLoop()
