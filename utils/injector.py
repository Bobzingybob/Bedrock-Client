"""
injector.py - DLL injection into Minecraft.Windows.exe

Uses the standard CreateRemoteThread + LoadLibraryW technique to inject
the custom BedrockBoost.dll into the running Minecraft process.

Requires admin privileges for UWP-injected processes.
"""

import ctypes
import ctypes.wintypes
import os
import struct
import sys
import time
from pathlib import Path

import psutil

# Windows API constants
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_CREATE_THREAD = 0x0002
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_ALL_ACCESS = 0x001F0FFF

CREATE_SUSPENDED = 0x00000004

# Windows API types
HANDLE = ctypes.c_void_p
LPVOID = ctypes.c_void_p
SIZE_T = ctypes.c_size_t
DWORD = ctypes.wintypes.DWORD
LPDWORD = ctypes.POINTER(DWORD)
LPTHREAD_START_ROUTINE = ctypes.c_void_p

# Load kernel32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# OpenProcess
kernel32.OpenProcess.argtypes = [DWORD, ctypes.c_bool, DWORD]
kernel32.OpenProcess.restype = HANDLE

# VirtualAllocEx
kernel32.VirtualAllocEx.argtypes = [HANDLE, LPVOID, SIZE_T, DWORD, DWORD]
kernel32.VirtualAllocEx.restype = LPVOID

# WriteProcessMemory
kernel32.WriteProcessMemory.argtypes = [HANDLE, LPVOID, ctypes.c_char_p, SIZE_T, ctypes.POINTER(SIZE_T)]
kernel32.WriteProcessMemory.restype = ctypes.c_bool

# CreateRemoteThread
kernel32.CreateRemoteThread.argtypes = [HANDLE, LPVOID, SIZE_T, LPTHREAD_START_ROUTINE, LPVOID, DWORD, LPDWORD]
kernel32.CreateRemoteThread.restype = HANDLE

# WaitForSingleObject
kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
kernel32.WaitForSingleObject.restype = DWORD

# CloseHandle
kernel32.CloseHandle.argtypes = [HANDLE]
kernel32.CloseHandle.restype = ctypes.c_bool

# GetProcAddress
kernel32.GetProcAddress.argtypes = [HANDLE, ctypes.c_char_p]
kernel32.GetProcAddress.restype = LPVOID

# LoadLibraryA
kernel32.LoadLibraryA.argtypes = [ctypes.c_char_p]
kernel32.LoadLibraryA.restype = HANDLE

# VirtualFreeEx
kernel32.VirtualFreeEx.argtypes = [HANDLE, LPVOID, SIZE_T, DWORD]
kernel32.VirtualFreeEx.restype = ctypes.c_bool

# EnumProcessModules (psapi.dll)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
psapi.EnumProcessModulesEx.argtypes = [HANDLE, ctypes.POINTER(HANDLE), DWORD, ctypes.POINTER(DWORD), DWORD]
psapi.EnumProcessModulesEx.restype = ctypes.c_bool

# GetModuleInformation (psapi.dll)
LPMODULEINFO = ctypes.Structure
LPMODULEINFO._fields_ = [
    ("lpBaseOfDll", LPVOID),
    ("SizeOfImage", DWORD),
    ("EntryPoint", LPVOID),
]
psapi.GetModuleInformation.argtypes = [HANDLE, HANDLE, ctypes.POINTER(LPMODULEINFO), DWORD]
psapi.GetModuleInformation.restype = ctypes.c_bool

# GetModuleFileNameExA (psapi.dll)
psapi.GetModuleFileNameExA.argtypes = [HANDLE, HANDLE, ctypes.c_char_p, DWORD]
psapi.GetModuleFileNameEx.restype = DWORD

MEM_COMMIT = 0x00001000
MEM_RESERVE = 0x00002000
MEM_RELEASE = 0x00008000
PAGE_READWRITE = 0x04
INFINITE = 0xFFFFFFFF
LIST_MODULES_ALL = 0x03


def get_kernel32_base_in_process(h_process):
    """Find the base address of kernel32.dll in the target process.
    
    UWP processes load kernel32.dll at a different address than the
    injector's process, so we can't use GetModuleHandleA from our process.
    Instead, we enumerate the target process's loaded modules.
    
    Args:
        h_process: Handle to the target process
        
    Returns:
        Base address of kernel32.dll in the target process, or 0 if not found
    """
    # Enumerate all modules in the target process
    module_handles = (HANDLE * 1024)()
    needed = DWORD()
    
    if not psapi.EnumProcessModulesEx(
        h_process,
        module_handles,
        DWORD(1024 * ctypes.sizeof(HANDLE)),
        ctypes.byref(needed),
        LIST_MODULES_ALL
    ):
        return 0
    
    module_count = needed.value // ctypes.sizeof(HANDLE)
    
    # Find kernel32.dll by checking module names
    for i in range(module_count):
        h_module = module_handles[i]
        name_buf = ctypes.create_string_buffer(260)
        
        if psapi.GetModuleFileNameExA(h_process, h_module, name_buf, 260) > 0:
            name = name_buf.value.decode('utf-8', errors='replace').lower()
            if 'kernel32.dll' in name or 'kernel32' in name:
                # Found kernel32.dll, return its base address (the module handle IS the base)
                return h_module
    
    return 0


def find_minecraft_process():
    """Find the running Minecraft.Windows.exe process.
    
    Returns the psutil.Process object or None if not found.
    """
    target = "Minecraft.Windows.exe"
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'].lower() == target.lower():
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def wait_for_minecraft(timeout=90):
    """Wait for Minecraft.Windows.exe to start and reach the title screen.
    
    Args:
        timeout: Maximum seconds to wait (default 90)
    
    Returns:
        psutil.Process object or None if timeout
    """
    start = time.time()
    while time.time() - start < timeout:
        proc = find_minecraft_process()
        if proc:
            # Wait a bit more for the title screen to load
            time.sleep(3)
            return proc
        time.sleep(1)
    return None


def inject_dll(pid, dll_path):
    """Inject a DLL into a process using CreateRemoteThread + LoadLibraryW.
    
    Args:
        pid: Process ID to inject into
        dll_path: Absolute path to the DLL file
    
    Returns:
        True if injection succeeded, False otherwise
    """
    dll_path = str(dll_path)
    if not os.path.isabs(dll_path):
        print(f"[!] DLL path must be absolute: {dll_path}")
        return False
    
    if not os.path.exists(dll_path):
        print(f"[!] DLL not found: {dll_path}")
        return False
    
    print(f"[i] Injecting {dll_path} into PID {pid}...")
    
    try:
        # Open the target process
        h_process = kernel32.OpenProcess(
            PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION,
            False,
            pid
        )
        if not h_process:
            err = ctypes.get_last_error()
            print(f"[!] Failed to open process (error {err})")
            if err == 5:
                print("[!] Access denied - try running as administrator")
            return False
        
        # Get LoadLibraryA address in the TARGET process
        # For UWP apps, kernel32.dll is loaded at a different address than in our process,
        # so we must find it by enumerating the target's loaded modules
        h_kernel32_remote = get_kernel32_base_in_process(h_process)
        if not h_kernel32_remote:
            print("[!] Failed to find kernel32.dll in target process")
            kernel32.CloseHandle(h_process)
            return False
        
        # Get LoadLibraryA offset from our own kernel32.dll (offsets are the same)
        h_kernel32_local = kernel32.GetModuleHandleA(b"kernel32.dll")
        load_lib_local = kernel32.GetProcAddress(h_kernel32_local, b"LoadLibraryA")
        if not load_lib_local:
            print("[!] Failed to get LoadLibraryA address from local kernel32")
            kernel32.CloseHandle(h_process)
            return False
        
        # Calculate the offset of LoadLibraryA within kernel32.dll
        load_lib_offset = load_lib_local - h_kernel32_local
        # Apply the same offset to the remote kernel32 base
        load_lib_addr = h_kernel32_remote + load_lib_offset
        
        print(f"[i] kernel32.dll base in target: 0x{h_kernel32_remote:X}")
        print(f"[i] LoadLibraryA address in target: 0x{load_lib_addr:X}")
        
        # Allocate memory in the target process
        dll_bytes = dll_path.encode('ascii') + b'\x00'
        alloc_addr = kernel32.VirtualAllocEx(
            h_process,
            0,
            len(dll_bytes),
            MEM_COMMIT | MEM_RESERVE,
            PAGE_READWRITE
        )
        if not alloc_addr:
            print("[!] Failed to allocate memory in target process")
            kernel32.CloseHandle(h_process)
            return False
        
        # Write DLL path to allocated memory
        written = SIZE_T()
        success = kernel32.WriteProcessMemory(
            h_process,
            alloc_addr,
            dll_bytes,
            len(dll_bytes),
            ctypes.byref(written)
        )
        if not success or written.value != len(dll_bytes):
            print("[!] Failed to write DLL path to target process")
            kernel32.VirtualFreeEx(h_process, alloc_addr, 0, MEM_RELEASE)
            kernel32.CloseHandle(h_process)
            return False
        
        # Create remote thread to load DLL
        h_thread = kernel32.CreateRemoteThread(
            h_process,
            None,
            0,
            load_lib_addr,
            alloc_addr,
            0,
            None
        )
        if not h_thread:
            print("[!] Failed to create remote thread")
            kernel32.VirtualFreeEx(h_process, alloc_addr, 0, MEM_RELEASE)
            kernel32.CloseHandle(h_process)
            return False
        
        # Wait for thread to finish
        result = kernel32.WaitForSingleObject(h_thread, INFINITE)
        
        # Cleanup
        kernel32.CloseHandle(h_thread)
        kernel32.VirtualFreeEx(h_process, alloc_addr, 0, MEM_RELEASE)
        kernel32.CloseHandle(h_process)
        
        print("[+] DLL injection successful")
        return True
        
    except Exception as e:
        print(f"[!] Injection failed: {e}")
        return False


def inject_client_dll(dll_path=None, timeout=90):
    """Full injection workflow: wait for Minecraft, inject DLL.
    
    Args:
        dll_path: Path to the DLL. If None, looks in client/build/BedrockBoost.dll
        timeout: Seconds to wait for Minecraft to start
    
    Returns:
        True if injection succeeded, False otherwise
    """
    import bedrock_boost_win
    script_dir = Path(bedrock_boost_win.__file__).resolve().parent
    
    # Default DLL path
    if dll_path is None:
        dll_path = script_dir / "client" / "build" / "Release" / "BedrockBoost.dll"
    else:
        dll_path = Path(dll_path)
    
    # Check DLL exists
    if not dll_path.exists():
        print(f"[!] Client DLL not found: {dll_path}")
        print("[i] Build the client first (see Step 4 of the plan)")
        return False
    
    # Wait for Minecraft
    print("[i] Waiting for Minecraft.Windows.exe...")
    proc = wait_for_minecraft(timeout)
    
    if not proc:
        print("[!] Minecraft did not start within timeout")
        return False
    
    print(f"[+] Found Minecraft (PID {proc.pid})")
    
    # Inject
    success = inject_dll(proc.pid, str(dll_path.resolve()))
    
    if success:
        print("[+] Client DLL injected successfully")
    else:
        print("[!] Injection failed - game will run without custom client")
    
    return success


def check_injection_ready():
    """Check if the system is ready for DLL injection.
    
    Returns:
        (bool, str): (ready, reason)
    """
    # Check admin privileges
    is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    if not is_admin:
        return False, "Admin privileges required for DLL injection"
    
    # Check Developer Mode (required for UWP injection)
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AppModelUnlock",
            0,
            winreg.KEY_READ
        )
        value, _ = winreg.QueryValueEx(key, "AllowAllTrustedApps")
        winreg.CloseKey(key)
        if value != 1:
            return False, "Windows Developer Mode is not enabled"
    except FileNotFoundError:
        return False, "Windows Developer Mode is not enabled"
    except Exception:
        pass  # Continue even if we can't check
    
    return True, "Ready"


def ensure_developer_mode():
    """Check and prompt for Developer Mode if needed."""
    ready, reason = check_injection_ready()
    if ready:
        return True
    
    print(f"[!] {reason}")
    print("[i] To enable Developer Mode:")
    print("[i] 1. Open Windows Settings")
    print("[i] 2. Go to Privacy & security > For developers")
    print("[i] 3. Turn on Developer Mode")
    print("[i] 4. Restart the launcher")
    return False
