'Retain only actually observed GPU memory values, with freshness.'
import time
class LastVRAM:
    def __init__(self):
        self.value=None
        self.at=None
    def apply(self,sample,now=None):
        now=time.monotonic() if now is None else now
        output=dict(sample)
        used=sample.get('vram_used')
        total=sample.get('vram_total')
        valid=(type(used) is int and type(total) is int and total>0 and 0<=used<=total)
        if valid:
            self.value=used; self.at=now
            output['vram_value_state']='current'
            output['vram_value_age_s']=0
        elif self.value is not None:
            output['vram_used']=self.value
            output['vram_value_state']='last'
            output['vram_value_age_s']=round(max(now-self.at,0),1)
        else:
            output['vram_value_state']='unavailable'
            output['vram_value_age_s']=None
        return output
