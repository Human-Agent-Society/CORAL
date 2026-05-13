import numpy as np
import os
import sys
from dataclasses import dataclass, field
from typing import Optional, Union, List, Callable, Optional
import threading

# COMPILE-TIME PARAMETERS
VIOBLK_INTR_PRIO = 1
VIOBLK_NAME = "vioblk"
VIOBLK_IRQ_PRIO = 1

# INTERNAL CONSTANT DEFINITIONS
VIRTIO_BLK_F_SIZE_MAX = 1
VIRTIO_BLK_F_SEG_MAX = 2
VIRTIO_BLK_F_GEOMETRY = 4
VIRTIO_BLK_F_RO = 5
VIRTIO_BLK_F_BLK_SIZE = 6
VIRTIO_BLK_F_FLUSH = 9
VIRTIO_BLK_F_TOPOLOGY = 10
VIRTIO_BLK_F_CONFIG_WCE = 11
VIRTIO_BLK_F_MQ = 12
VIRTIO_BLK_F_DISCARD = 13
VIRTIO_BLK_F_WRITE_ZEROES = 14
VIRTIO_BLK_F_LIFETIME = 15
VIRTIO_BLK_F_SECURE_ERASE = 16

# Virtio device status bits
VIRTIO_STAT_ACKNOWLEDGE = (1 << 0)
VIRTIO_STAT_DRIVER = (1 << 1)
VIRTIO_STAT_FEATURES_OK = (1 << 3)
VIRTIO_STAT_DRIVER_OK = (1 << 2)
VIRTIO_STAT_DEVICE_NEEDS_RESET = (1 << 6)
VIRTIO_STAT_FAILED = (1 << 7)

# Virtio feature bits (number, not mask)
VIRTIO_F_INDIRECT_DESC = 28
VIRTIO_F_EVENT_IDX = 29
VIRTIO_F_ANY_LAYOUT = 27
VIRTIO_F_RING_RESET = 40
VIRTIO_F_IN_ORDER = 35

# Virtqueue constants
VIRTQ_LEN_MAX = 32768

VIRTQ_USED_F_NO_NOTIFY = 1
VIRTQ_AVAIL_F_NO_INTERRUPT = 1

VIRTQ_DESC_F_NEXT = (1 << 0)
VIRTQ_DESC_F_WRITE = (1 << 1)
VIRTQ_DESC_F_INDIRECT = (1 << 2)

# Feature vector length
VIRTIO_FEATLEN = 4

# Virtio interrupt status bits
USED_BUFFER_NOTIFICATION = (1 << 0)
CONFIGURATION_CHANGE_NOTIFICATION = (1 << 1)


# vioblk vq request type
VIRTIO_BLK_T_IN = 0
VIRTIO_BLK_T_OUT = 1


@dataclass
class Geometry:
    cylinders: int  # uint16_t
    heads: int      # uint8_t
    sectors: int    # uint8_t

@dataclass
class Topology:
    physical_block_exp: int   # uint8_t
    alignment_offset: int     # uint8_t
    min_io_size: int          # uint16_t
    opt_io_size: int          # uint32_t

@dataclass
class BlockConfig:
    capacity: int                  # uint64_t
    size_max: int                  # uint32_t
    seg_max: int                   # uint32_t
    geometry: Geometry
    blk_size: int                  # uint32_t
    topology: Topology
    writeback: int                 # uint8_t
    unused0: int                   # char
    num_queues: int                # uint16_t
    max_discard_sectors: int        # uint32_t
    max_discard_seg: int            # uint32_t
    discard_sector_alignment: int  # uint32_t
    max_write_zeroes_sectors: int   # uint32_t
    max_write_zeroes_seg: int       # uint32_t
    write_zeroes_may_unmap: int     # uint8_t
    max_secure_erase_sectors: int   # uint32_t
    max_secure_erase_seg: int       # uint32_t
    secure_erase_sector_alignment: int  # uint32_t


@dataclass
class VirtioMmioRegs:
    magic_value: int               = 0  # uint32_t
    version: int                   = 0  # uint32_t
    device_id: int                 = 0  # uint32_t
    vendor_id: int                 = 0  # uint32_t
    device_features: int           = 0  # uint32_t
    device_features_sel: int       = 0  # uint32_t
    driver_features: int           = 0  # uint32_t
    driver_features_sel: int       = 0  # uint32_t
    queue_sel: int                 = 0  # uint32_t
    queue_num_max: int             = 0  # uint32_t
    queue_num: int                 = 0  # uint32_t
    queue_ready: int               = 0  # uint32_t
    queue_notify: int              = 0  # uint32_t
    interrupt_status: int          = 0  # uint32_t
    interrupt_ack: int             = 0  # uint32_t
    status: int                    = 0  # uint32_t
    queue_desc: int                = 0  # uint64_t
    queue_driver: int              = 0  # uint64_t
    queue_device: int              = 0  # uint64_t
    shm_sel: int                   = 0  # uint32_t
    shm_len: int                   = 0  # uint64_t
    shm_base: int                  = 0  # uint64_t
    queue_reset: int               = 0  # uint32_t


    config: Union[BlockConfig, bytes] = field(default_factory=lambda: BlockConfig(
        capacity=4,
        size_max=512,
        seg_max=1,
        geometry=Geometry(cylinders=1, heads=1, sectors=4),
        blk_size=512,
        topology=Topology(physical_block_exp=0, alignment_offset=0, min_io_size=512, opt_io_size=512),
        writeback=0,
        unused0=0,
        num_queues=1,
        max_discard_sectors=0,
        max_discard_seg=0,
        discard_sector_alignment=0,
        max_write_zeroes_sectors=0,
        max_write_zeroes_seg=0,
        write_zeroes_may_unmap=0,
        max_secure_erase_sectors=0,
        max_secure_erase_seg=0,
        secure_erase_sector_alignment=0
    ))



# 定义 iointf 接口
@dataclass
class IoIntf:
    close: Optional[Callable[['Io'], None]]
    cntl: Optional[Callable[['Io', int, object], int]]
    read: Optional[Callable[['Io', int, object, int], int]]
    write: Optional[Callable[['Io', int, object, int], int]]

# 定义 io 结构体
@dataclass
class Io:
    intf: Optional[IoIntf]
    refcnt: int


@dataclass
class VirtqDesc:
    addr: int = -1        # uint64_t
    len: int = -1        # uint32_t
    flags: int = -1      # uint16_t
    next: int = -1        # int16_t

@dataclass
class VirtqAvail:
    flags: int = 0       # uint16_t
    idx: int = 0        # uint16_t
    ring: List[int] = field(default_factory=list)  # 动态数组


@dataclass
class VirtqUsedElem:
    id: int = 0   # uint32_t
    len: int = 0  # uint32_t

@dataclass
class VirtqUsed:
    flags: int = 0        # uint16_t
    idx: int  = 0         # uint16_t
    ring: List[VirtqUsedElem] = field(default_factory=list)  # 动态数组

def virtio_notify_avail(regs: VirtioMmioRegs, qid: int) -> None:
    regs.queue_notify = qid



## Thread and Condition Variable
@dataclass
class Thread:
    id: int = -1

curr_thread = Thread(id = 1)

@dataclass
class ThreadList:
    threads: List[Thread] = field(default_factory=list)

    def add_thread(self, thread: Thread):
        self.threads.append(thread)

    def clear(self):
        self.threads.clear()

@dataclass
class Condition:
    name: Optional[str] = None
    wait_list: ThreadList = field(default_factory=ThreadList)
    is_used: int = 0


def condition_init(cond: Condition, name: Optional[str] = None):
    cond.name = name
    cond.wait_list = ThreadList()
    cond.is_used = 0

def condition_wait(cond: Condition, thread: Thread):
    if vioblk.vq.last_used_idx == vioblk.vq.used.idx:
        if vioblk.vq.req.type == VIRTIO_BLK_T_IN:
            vioblk.vq.used.idx += 1
            cond.is_used = 1    # read using condition
            vioblk.regs.interrupt_status |= USED_BUFFER_NOTIFICATION
            vioblk.vq.status = 0
            
            vioblk.readbuf[:] = vioblk.vioblk_content[vioblk.vq.req.sector * 512 : (vioblk.vq.req.sector+1) * 512]
        
        elif vioblk.vq.req.type == VIRTIO_BLK_T_OUT:
            vioblk.vq.used.idx += 1
            cond.is_used = 2 # write using condition
            vioblk.regs.interrupt_status |= USED_BUFFER_NOTIFICATION
            vioblk.vq.status = 0

            vioblk.vioblk_content[vioblk.vq.req.sector * 512 : (vioblk.vq.req.sector+1) * 512] = vioblk.writebuf[:]
    cond.wait_list.add_thread(thread)

def condition_broadcast(cond: Condition):
    cond.wait_list.clear()



# Lock
@dataclass
class Lock:
    owner: Optional[Thread] = None
    lkrelease: Condition = field(default_factory=Condition)
    accessed = 0

# Helper functions

def lock_init(lock: Lock):
    lock.owner = None
    lock.lkrelease = Condition()
    lock.accessed = 0

def lock_acquire(lock: Lock, thread: Thread):
    if lock.owner is None:
        lock.owner = thread
        lock.accessed = 1
    elif lock.owner == thread:
        pass
    else:
        condition_wait(lock.lkrelease, thread)

def lock_release(lock: Lock):
    lock.owner = None
    condition_broadcast(lock.lkrelease)


# vioblk_req
@dataclass
class VioblkReq:
    type: int
    reserved: int
    sector: int

# vioblk_device
@dataclass
class VioblkDevice:
    regs: VirtioMmioRegs
    io: Io
    irqno: int = 2
    instno: int = 0


    @dataclass
    class Vq:
        last_used_idx: int = 0

        avail: Union[VirtqAvail, bytes] = field(default_factory=lambda: VirtqAvail())

        used: Union[VirtqUsed, bytes] = field(default_factory=lambda: VirtqUsed())   # 填充
        desc: list = field(default_factory=lambda: [VirtqDesc() for _ in range(4)])  # 4 descriptors

        req: VioblkReq = field(default_factory=lambda: VioblkReq(-1, -1, -1))
        status: int = 0

    vq: Vq = field(default_factory=Vq)

    readbufcnt: int = 0
    readbuf = bytearray(512)

    writebufcnt: int = 0
    writebuf = bytearray(512)

    vioblk_used_updated: Condition = field(default_factory=Condition)
    vioblk_lock: Lock = field(default_factory=Lock)

    blksz: int = 512
    is_open: int = 1
    pos: int = 0
    capacity: int = 2048

    vioblk_content = bytearray(2048)

# intr
spie: int = 1
intr_used = 0
def disable_interrupts():
    global spie
    global intr_used
    intr_used = 1
    orig = spie
    spie = 0
    return orig

def restore_interrupts(orig: int):
    global spie
    spie = orig

def enable_interrupts():
    global spie
    global intr_used
    intr_used = 2
    orig = spie
    spie = 1
    return orig


vioblkregs = VirtioMmioRegs()
vioblkio = Io(refcnt = 0, intf=None)
vioblk = VioblkDevice(regs=vioblkregs, io=vioblkio)
origin_data = b"Per Aspera, Ad Astra"
vioblk.vioblk_content[80:80+len(origin_data)] = origin_data


# class ReadThread(threading.Thread):
#     def __init__(self, vioblk:VioblkDevice, readbuf:bytearray):
#         super().__init__()
#         self.vioblk : VioblkDevice = vioblk
#         self.readbuf : bytearray = readbuf
#         self.error = None

#     def run(self):
#         try:
#             self.vioblk.io.intf.read(self.vioblk, 0, self.readbuf, 512)
#         except Exception as e:
#             self.error = e




def evaluate_llm_response(llm_response):
# def evaluate_llm_response():
    # print(llm_response)

    # Set up return values
    passed = False
    details = dict()
    score = 0
    confidence = 100

    pass_flag = 1

    


    # Set up testing environments
    vioblk.regs.queue_notify = -1
    condition_init(vioblk.vioblk_used_updated, "used_updated")
    lock_init(vioblk.vioblk_lock)
    data = b"xxx"
    vioblk.vioblk_content[:len(data)] = data
    vioblk.vq.avail.ring.append(-1)
    vioblk.vq.avail.ring.append(-1)
    vioblk.vq.avail.ring.append(-1)
    vioblk.vq.avail.ring.append(-1)


    writebuf = bytearray(1024)
    mystr = b"Per Aspera, Ad Astra" * 50
    writebuf[:len(mystr)] = mystr
    readbuf = bytearray(1024)

    try:
        # def vioblk_read(vioblk:VioblkDevice, pos: int, buf: bytes, len: int)
        namespace = {}
        all_code = llm_response.config.vioblk_write + "\n" + llm_response.config.vioblk_read
        exec(all_code, globals(), namespace)
        vioblk_write = namespace['vioblk_write']
        vioblk_read = namespace['vioblk_read']
        # vioblk_read = gold_vioblk_read
        # vioblk_write = gold_vioblk_write

        vioblkio.intf = IoIntf(close=None, cntl=None, read=vioblk_read, write=vioblk_write)


        print("Testing Robustness......")
        try:
            pos = 0
            length = 0
            ret = vioblk_write(None, pos, writebuf, length)
            if ret == -1:
                score += 2.5
                details["Can handle no device"] = "passed"
            
            else:
                pass_flag = 0
                details["Can handle no device"] = "failed"

        except Exception as e:
            pass_flag = 0
            details["Can handle no device"] = str(e)
        
        try:
            pos = 0
            length = 0
            ret = vioblk_write(vioblk, pos, None, length)
            if ret == -1:
                score += 2.5
                details["Can handle no write buf"] = "passed"
            else:
                pass_flag = 0
                details["Can handle no write buf"] = "failed"

        except Exception as e:
            pass_flag = 0
            details["Can handle no write buf"] = str(e)
        
        try:
            pos = 4096
            length = 0
            ret = vioblk_write(vioblk, pos, writebuf, length)
            if ret == -1:
                score += 2.5
                details["Can handle pos out of capacity"] = "passed"
            else:
                pass_flag = 0
                details["Can handle pos out of capacity"] = "failed"

        except Exception as e:
            pass_flag = 0
            details["Can handle pos out of capacity"] = str(e)
        
        try:
            pos = 1024
            length = 4096
            ret = vioblk_write(vioblk, pos, writebuf, length)
            if ret == 1024:
                score += 2.5
                details["Can handle write range out of capacity"] = "passed"
            else:
                pass_flag = 0
                details["Can handle write range out of capacity"] = "failed"

        except Exception as e:
            pass_flag = 0
            details["Can handle write range out of capacity"] = str(e)
        

        print("Testing Others......")

        # Set up testing environments
        vioblk.regs.queue_notify = -1
        condition_init(vioblk.vioblk_used_updated, "used_updated")
        lock_init(vioblk.vioblk_lock)
        data = b"xxx"
        vioblk.vioblk_content[:len(data)] = data
        vioblk.vq.avail.ring.append(-1)
        vioblk.vq.avail.ring.append(-1)
        vioblk.vq.avail.ring.append(-1)
        vioblk.vq.avail.ring.append(-1)

        try:
        # details = {}
        # readbuf = bytearray(512)
        # read_thread = ReadThread(vioblk, readbuf)
        # read_thread.start()
        # read_thread.join(timeout=8)

        # if read_thread.is_alive():
        #     pass_flag = 0
        #     details["Other errors"] = "Timeout during vioblk_read"
            
        # else:
        #     if read_thread.error:
        #         pass_flag = 0
        #         details["Other errors"] = str(read_thread.error)
            pos = 80
            length = len(origin_data)
            ret = vioblk_read(vioblk, pos, readbuf, length)

            ## Full Read
            if ret == length:
                score += 10
                details["Successfully read characters of the specified length"] = "Passed"
            else:
                details["Successfully read characters of the specified length"] = "Failed"
                pass_flag = 0
            
            ## Correctly reads the data
            if readbuf[:length] == origin_data:
                score += 10
                details["Correctly reads the data"] = "Passed"
            else:
                details["Correctly reads the data"] = "Failed"
                pass_flag = 0

            vioblk.vioblk_content[:2013] = b"xxx" + b"\x00"*2010

            pos = 3
            length = len(mystr)
            ret = vioblk_write(vioblk, pos, writebuf, length)

            ## Full Write
            if ret == length:
                score += 10
                details["Successfully write characters of the specified length"] = "Passed"
            else:
                details["Successfully write characters of the specified length"] = "Failed"
                pass_flag = 0
            
            ## correctly acquires and releases the lock
            if vioblk.vioblk_lock.accessed == 1 and vioblk.vioblk_lock.owner == None:
                score += 5
                details["Correctly acquires and releases the lock"] = "Passed"
            else:
                details["Correctly acquires and releases the lock"] = "Failed"
                pass_flag = 0
            
            ## Correctly disables and restores the interrupt
            global intr_used
            global spie
            if spie == 1 and intr_used == 1:
                score += 5
                details["Correctly disables and restores the interrupt"] = "Passed"
            else:
                details["Correctly disables and restores the interrupt"] = "Failed"
                pass_flag = 0
            
            ## correctly sets up the vq
            if vioblk.vq.req.type == VIRTIO_BLK_T_OUT:
                score += 1
                details["Correctly set up the virtqueue request header"] = "Passed"
            else:
                details["Correctly set up the virtqueue request header"] = "Failed"
                pass_flag = 0

            ## The indirect descriptor case
            if vioblk.vq.desc[0].flags == VIRTQ_DESC_F_INDIRECT:
                if vioblk.vq.desc[0].addr == id(vioblk.vq.desc[1]) \
                    and vioblk.vq.desc[0].len == 3 * 16:

                    score += 2
                    details["Setting of indirect desc[0]"] = "Passed"
                else:
                    details["Setting of indirect desc[0]"] = "Failed"
                    pass_flag = 0
                
                if vioblk.vq.desc[1].addr == id(vioblk.vq.req) \
                    and vioblk.vq.desc[1].len == 16 \
                    and vioblk.vq.desc[1].flags == VIRTQ_DESC_F_NEXT \
                    and vioblk.vq.desc[1].next == 1:

                    score += 3
                    details["Setting of indirect desc[1]"] = "Passed"
                else:
                    details["Setting of indirect desc[1]"] = "Failed"
                    pass_flag = 0

                if vioblk.vq.desc[2].addr == id(vioblk.writebuf) \
                    and vioblk.vq.desc[2].len == vioblk.blksz \
                    and (vioblk.vq.desc[2].flags == VIRTQ_DESC_F_NEXT) \
                    and vioblk.vq.desc[2].next == 2:
                    
                    score += 5
                    details["Setting of indirect desc[2]"] = "Passed"
                else:
                    details["Setting of indirect desc[2]"] = "Failed"
                    pass_flag = 0

                if vioblk.vq.desc[3].addr == id(vioblk.vq.status) \
                    and vioblk.vq.desc[3].len == 1 \
                    and vioblk.vq.desc[3].flags == VIRTQ_DESC_F_WRITE \
                    and vioblk.vq.desc[3].next == 0:

                    score += 5
                    details["Setting of indirect desc[3]"] = "Passed"
                else:
                    details["Setting of indirect desc[3]"] = "Failed"
                    pass_flag = 0

            ## The direct descriptor case
            elif vioblk.vq.desc[0].flags == VIRTQ_DESC_F_NEXT:
                if vioblk.vq.desc[0].addr == id(vioblk.vq.req) \
                    and vioblk.vq.desc[0].len == 16 \
                    and vioblk.vq.desc[0].flags == VIRTQ_DESC_F_NEXT \
                    and vioblk.vq.desc[0].next == 1:

                    score += 5
                    details["Setting of direct desc[0]"] = "Passed"
                else:
                    details["Setting of direct desc[0]"] = "Failed"
                    pass_flag = 0

                if vioblk.vq.desc[1].addr == id(vioblk.writebuf) \
                    and vioblk.vq.desc[1].len == vioblk.blksz \
                    and (vioblk.vq.desc[1].flags == VIRTQ_DESC_F_NEXT) \
                    and vioblk.vq.desc[1].next == 2:
                    
                    score += 5
                    details["Setting of direct desc[1]"] = "Passed"
                else:
                    details["Setting of direct desc[1]"] = "Failed"
                    pass_flag = 0

                if vioblk.vq.desc[2].addr == id(vioblk.vq.status) \
                    and vioblk.vq.desc[2].len == 1 \
                    and vioblk.vq.desc[2].flags == VIRTQ_DESC_F_WRITE \
                    and vioblk.vq.desc[2].next == 0:
                    
                    score += 5
                    details["Setting of direct desc[2]"] = "Passed"
                else:
                    details["Setting of direct desc[2]"] = "Failed"
                    pass_flag = 0
            
            else:
                pass_flag = 0
            
            if vioblk.vq.avail.ring[0] == 0:
                score += 2
                details["Correctly set up the available virtqueue"] = "Passed"
            else:
                details["Correctly set up the available virtqueue"] = "Failed"
                pass_flag = 0
            
            ## Correctly sets up the used queue:
            if vioblk.vq.last_used_idx == vioblk.vq.used.idx:
                score += 2
                details["Correctly set up the used virtqueue"] = "Passed"
            else:
                details["Correctly set up the used virtqueue"] = "Failed"
                pass_flag = 0

            ## Correctly notifies the device
            if vioblk.regs.queue_notify == 0:
                score += 10
                details["Correctly notifies the device"] = "Passed"
            else:
                details["Correctly notifies the device"] = "Failed"
                pass_flag = 0

            ## Correctly waits for the cond variable
            if vioblk.vioblk_used_updated.is_used == 2:
                score += 10
                details["Correctly waits for the condition variable"] = "Passed"
            else:
                details["Correctly waits for the condition variable"] = "Failed"
                pass_flag = 0

            ## Correctly writes the data
            expected = b"xxx" + b"Per Aspera, Ad Astra"*50 + b"\x00\x00\x00"
            n = len(expected)

            if vioblk.vioblk_content[:n] == expected:
                score += 10
                details["Correctly writes the data"] = "Passed"
            else:
                details["Correctly writes the data"] = "Failed"
                pass_flag = 0


        except Exception as e:
            pass_flag = 0
            details["other tests"] = str(e)

        if pass_flag == 1:
            passed = True
        
        # print(vioblk.vioblk_content)
        
        print("Vioblk read and write union test finished.")
        return passed, details, score, confidence


    except Exception as e:
        print("Error occurred in test. Saved and exited.")
        return False, {"error": str(e)}, None, None
    








def gold_vioblk_read(vioblk:VioblkDevice, pos: int, buf: bytes, len: int) -> int:
    if not vioblk:
        return -1  # -EINVAL

    if not buf:
        return -1  # -EINVAL


    qid = 0  # only one vq, id is 0

    bytes_read = 0  # number of bytes that have been read

    if pos >= vioblk.capacity:
        return -1  # -EINVAL

    len = (vioblk.capacity - pos) if (pos + len >= vioblk.capacity) else len

    if len <= 0:
        return bytes_read  # 0 bytes read

    lock_acquire(vioblk.vioblk_lock, curr_thread)

    while bytes_read < len:
        bytes_to_read = vioblk.blksz if (len - bytes_read > vioblk.blksz) else (len - bytes_read)
        if bytes_to_read > (vioblk.blksz - ((pos + bytes_read) % vioblk.blksz)):
            bytes_to_read = vioblk.blksz - ((pos + bytes_read) % vioblk.blksz)

        if bytes_to_read == 0:
            break

        vioblk.vq.req.sector = (pos + bytes_read) // vioblk.blksz
        vioblk.vq.req.type = VIRTIO_BLK_T_IN

        vioblk.vq.desc[0].addr = id(vioblk.vq.desc[1])
        vioblk.vq.desc[0].len = 3 * 16  # sizeof(struct virtq_desc) == 16
        vioblk.vq.desc[0].flags = VIRTQ_DESC_F_INDIRECT

        vioblk.vq.desc[1].addr = id(vioblk.vq.req)
        vioblk.vq.desc[1].len = 16  # sizeof(struct vioblk_req) == 16
        vioblk.vq.desc[1].flags = VIRTQ_DESC_F_NEXT
        vioblk.vq.desc[1].next = 1

        vioblk.vq.desc[2].addr = id(vioblk.readbuf)
        vioblk.vq.desc[2].len = vioblk.blksz
        vioblk.vq.desc[2].flags = VIRTQ_DESC_F_NEXT | VIRTQ_DESC_F_WRITE
        vioblk.vq.desc[2].next = 2

        vioblk.vq.desc[3].addr = id(vioblk.vq.status)
        vioblk.vq.desc[3].len = 1  # sizeof(uint8_t)
        vioblk.vq.desc[3].flags = VIRTQ_DESC_F_WRITE
        vioblk.vq.desc[3].next = 0

        vioblk.vq.avail.flags = 0
        qsz = 4
        head = 0
        vioblk.vq.avail.ring[vioblk.vq.avail.idx % qsz] = head
        vioblk.vq.avail.idx += 1


        id_backup = disable_interrupts()

        virtio_notify_avail(vioblk.regs, qid)

        while vioblk.vq.last_used_idx == vioblk.vq.used.idx:
            condition_wait(vioblk.vioblk_used_updated, curr_thread)
        vioblk.vq.last_used_idx += 1

        restore_interrupts(id_backup)

        read_pos = (pos + bytes_read) % vioblk.blksz
        if vioblk.readbuf is None:
            lock_release(vioblk.vioblk_lock)
            return -1
        buf[bytes_read:bytes_read + bytes_to_read] = vioblk.readbuf[read_pos:read_pos + bytes_to_read]

        bytes_read += bytes_to_read

    lock_release(vioblk.vioblk_lock)

    return bytes_read

### Gold Solution Here ###
def gold_vioblk_write(vioblk:VioblkDevice, pos: int, buf: bytes, len: int) -> int:
    if not vioblk:
        return -1  # -EINVAL

    if not buf:
        return -1  # -EINVAL


    qid = 0  # only one vq, id is 0

    bytes_written = 0  # number of bytes that have been read

    if pos >= vioblk.capacity:
        return -1  # -EINVAL

    len = (vioblk.capacity - pos) if (pos + len >= vioblk.capacity) else len

    if len <= 0:
        return bytes_written  # 0 bytes read

    lock_acquire(vioblk.vioblk_lock, curr_thread)

    while bytes_written < len:
        bytes_to_write = vioblk.blksz if (len - bytes_written > vioblk.blksz) else (len - bytes_written)

        gold_vioblk_read(vioblk, ((pos + bytes_written) // vioblk.blksz) * vioblk.blksz, vioblk.writebuf, vioblk.blksz)

        if bytes_to_write > (vioblk.blksz - ((pos + bytes_written) % vioblk.blksz)):
            bytes_to_write = vioblk.blksz - ((pos + bytes_written) % vioblk.blksz)

        if bytes_to_write == 0:
            break

        write_pos = (pos + bytes_written) % vioblk.blksz
        vioblk.writebuf[write_pos:write_pos+bytes_to_write] = buf[bytes_written:bytes_written + bytes_to_write]

        # Now write into virtio
        vioblk.vq.req.sector = (pos + bytes_written) // vioblk.blksz
        vioblk.vq.req.type = VIRTIO_BLK_T_OUT

        vioblk.vq.desc[0].addr = id(vioblk.vq.desc[1])
        vioblk.vq.desc[0].len = 3 * 16  # sizeof(struct virtq_desc) == 16
        vioblk.vq.desc[0].flags = VIRTQ_DESC_F_INDIRECT

        vioblk.vq.desc[1].addr = id(vioblk.vq.req)
        vioblk.vq.desc[1].len = 16  # sizeof(struct vioblk_req) == 16
        vioblk.vq.desc[1].flags = VIRTQ_DESC_F_NEXT
        vioblk.vq.desc[1].next = 1

        vioblk.vq.desc[2].addr = id(vioblk.writebuf)
        vioblk.vq.desc[2].len = vioblk.blksz
        vioblk.vq.desc[2].flags = VIRTQ_DESC_F_NEXT
        vioblk.vq.desc[2].next = 2

        vioblk.vq.desc[3].addr = id(vioblk.vq.status)
        vioblk.vq.desc[3].len = 1  # sizeof(uint8_t)
        vioblk.vq.desc[3].flags = VIRTQ_DESC_F_WRITE
        vioblk.vq.desc[3].next = 0

        vioblk.vq.avail.flags = 0
        qsz = 4
        head = 0
        vioblk.vq.avail.ring[vioblk.vq.avail.idx % qsz] = head
        vioblk.vq.avail.idx += 1


        id_backup = disable_interrupts()

        virtio_notify_avail(vioblk.regs, qid)

        while vioblk.vq.last_used_idx == vioblk.vq.used.idx:
            condition_wait(vioblk.vioblk_used_updated, curr_thread)
        vioblk.vq.last_used_idx += 1

        restore_interrupts(id_backup)

        

        bytes_written += bytes_to_write

    lock_release(vioblk.vioblk_lock)

    return bytes_written


if __name__ == "__main__":
    print(evaluate_llm_response())
    # print(vioblk.vioblk_content)