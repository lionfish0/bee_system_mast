# bee_system
The full system to run on the flight raspberry pi

# Install Instructions
1. Download the aravis library:

    cd ~
    git clone https://github.com/AravisProject/aravis.git
    
2. Download this tool

   pip install git+https://github.com/lionfish0/bee_system.git

3. Add the relevant paths to make aravis work:

   export GI_TYPELIB_PATH=$GI_TYPELIB_PATH:~/aravis/src
   export LD_LIBRARY_PATH=~aravis/src/.libs

# System Requirements 

    pip install Flask


# Running it

<pre>export GI_TYPELIB_PATH=$GI_TYPELIB_PATH:/home/pi/aravis/src
export LD_LIBRARY_PATH=/home/pi/aravis/src/.libs

cd /home/pi/bee_system/webinterface 
/usr/bin/python3 -m http.server &



while :
do
	echo "RESTARTING!!!"
	/usr/bin/python3 /home/pi/bee_system/bee_system/__init__.py
done</pre>
