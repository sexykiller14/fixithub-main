@echo off
REM ===========================================================================
REM FixIT Hub - Network reset
REM
REM WHAT THIS DOES
REM   Resets Windows network settings. It flushes the DNS cache, releases and
REM   renews your network connection, rebuilds the Winsock catalog, and resets
REM   TCP/IP to its defaults.
REM
REM WHEN TO USE IT
REM   - Internet works on other devices but not this PC
REM   - Windows keeps saying "No internet access" when the router is fine
REM   - A VPN or virtual network adapter was removed badly
REM
REM WHAT IT CHANGES
REM   Yes. This modifies network configuration. Your VPN client and virtual
REM   machine networks may need to be reinstalled afterwards.
REM
REM TO RUN
REM   Right-click this file and choose "Run as administrator".
REM   You MUST restart Windows afterwards for the Winsock and TCP/IP resets to
REM   take effect.
REM
REM Review this file before running it. Every command is listed below with a
REM comment explaining what it does.
REM ===========================================================================

echo.
echo ============================================
echo  FixIT Hub - Network reset
echo ============================================
echo.

REM Check for administrator rights, since every command below needs them.
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click this file and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo [1/5] Clearing the DNS cache...
REM flushdns discards cached website name lookups so they are resolved fresh.
ipconfig /flushdns

echo [2/5] Releasing your current IP address...
REM release tells the network this computer no longer needs its assigned address.
ipconfig /release

echo [3/5] Requesting a new IP address...
REM renew asks the router or DHCP server for a fresh address and settings.
ipconfig /renew

echo [4/5] Rebuilding the Winsock catalog...
REM winsock reset rebuilds the list of network components Windows uses.
REM This is the step that fixes most broken connections.
REM A restart is required afterwards.
netsh winsock reset

echo [5/5] Resetting TCP/IP to defaults...
REM int ip reset undoes any manual IP address, gateway or DNS changes.
REM A restart is required afterwards.
netsh int ip reset

echo.
echo ============================================
echo  Done. Please restart your computer now.
echo ============================================
echo.
pause
