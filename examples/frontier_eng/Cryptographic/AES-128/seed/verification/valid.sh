OLD_PWD=$(pwd)
cd verification
g++ ../baseline/AES-128.cpp -o custom_aes -O3
g++ validate.cpp -o validate -lcrypto -O3
./validate
cd "$OLD_PWD"