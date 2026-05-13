OLD_PWD=$(pwd)
cd verification
g++ ../baseline/SHA-256.cpp -o custom_sha -O3
g++ validate.cpp -o validate -lcrypto -O3
./validate
cd "$OLD_PWD"