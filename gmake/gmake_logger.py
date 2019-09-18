import logging
import os

logger = logging.getLogger('gmake')

def logger_config(logfile=None,
                  loglevel='INFO',logfilelevel='INFO',
                  reset=True):
    """
    set up a customized logger,e.g.,
        >>>gmake.logger_config(logfile='logs/test_gmake.log',
                loglevel=logging.WARNING,
                logfilelevel=logging.INFO)
    
    """

    if  reset:
        logger.handlers=[]

    # note: we don't touch the root logger level here
    logger.setLevel(logging.DEBUG)
    
    #   file logging handler 

    if  logfile is not None:
        logdir=os.path.dirname(logfile)
        if  (not os.path.exists(logdir)) and (logdir!=''):
            os.makedirs(logdir)                
        logfile_handler=logging.FileHandler(logfile,mode='a')
        #format="%(asctime)s "+"{:<40}".format("%(name)s.%(funcName)s")+" [%(levelname)s] ::: %(message)s"
        #logfile_formatter=MultilineFormatter(format)
        logfile_formatter=CustomFormatter()
        logfile_handler.setFormatter(logfile_formatter)
        logfile_handler.setLevel(logfilelevel)
        logger.addHandler(logfile_handler)
    
    #   console logging handler
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(loglevel)        
    #console_formatter=CustomFormatter()
    #console_handler.setFormatter(console_formatter)            
    logger.addHandler(console_handler)
    
    return     

def logger_status():
    """
    print out the current status of gmake logger
    """
    print(logging.getLogger('gmake'))
    print(logging.getLogger('gmake').handlers)
    
    return

class CustomFormatter(logging.Formatter):
    """
    customized logging formatter which can handle mutiple-line msgs
    """
    def format(self, record:logging.LogRecord):
        save_msg = record.msg
        output = []
        datefmt='%Y-%m-%d %H:%M:%S'
        s = "{} :: {:<32} :: {:<8} :: ".format(self.formatTime(record, datefmt),
                                               record.name+'.'+record.funcName,
                                               "[" + record.levelname + "]")
        for line in save_msg.splitlines():
            record.msg = line
            output.append(s+line)
            
        output='\n'.join(output)
        record.msg = save_msg
        record.message = output

        return output            