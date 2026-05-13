// EVOLVE-BLOCK-START
#include <iostream>
#include <vector>
#include <iomanip>
#include <cstdint>
#include <string>
#include <fstream>
#include <sstream>




class AES128 {
private:
    static const uint8_t sbox[256];
    static const uint8_t Rcon[11];
    
    int Nk = 4, Nr = 10, Nb = 4;
    std::vector<uint8_t> RoundKey;

    uint8_t xtime(uint8_t x) { return (x << 1) ^ (((x >> 7) & 1) * 0x1b); }

    void SubWord(uint8_t* word) {
        for (int i = 0; i < 4; i++) word[i] = sbox[word[i]];
    }

    void RotWord(uint8_t* word) {
        uint8_t tmp = word[0];
        word[0] = word[1]; word[1] = word[2]; word[2] = word[3]; word[3] = tmp;
    }

    void KeyExpansion(const std::vector<uint8_t>& key) {
        RoundKey.resize(176);
        uint8_t temp[4];
        for (int i = 0; i < 16; i++) RoundKey[i] = key[i];
        int bytesGenerated = 16, rconIteration = 1;

        while (bytesGenerated < 176) {
            for (int i = 0; i < 4; i++) temp[i] = RoundKey[bytesGenerated - 4 + i];
            if (bytesGenerated % 16 == 0) {
                RotWord(temp);
                SubWord(temp);
                temp[0] ^= Rcon[rconIteration++];
            }
            for (int i = 0; i < 4; i++) {
                RoundKey[bytesGenerated] = RoundKey[bytesGenerated - 16] ^ temp[i];
                bytesGenerated++;
            }
        }
    }

    void AddRoundKey(uint8_t state[4][4], int round) {
        for (int c = 0; c < 4; c++) {
            for (int r = 0; r < 4; r++) {
                state[r][c] ^= RoundKey[round * 16 + c * 4 + r];
            }
        }
    }

    void SubBytes(uint8_t state[4][4]) {
        for (int r = 0; r < 4; r++) {
            for (int c = 0; c < 4; c++) state[r][c] = sbox[state[r][c]];
        }
    }

    void ShiftRows(uint8_t state[4][4]) {
        uint8_t temp;
        temp = state[1][0]; state[1][0] = state[1][1]; state[1][1] = state[1][2]; state[1][2] = state[1][3]; state[1][3] = temp;
        temp = state[2][0]; uint8_t temp2 = state[2][1]; state[2][0] = state[2][2]; state[2][1] = state[2][3]; state[2][2] = temp; state[2][3] = temp2;
        temp = state[3][3]; state[3][3] = state[3][2]; state[3][2] = state[3][1]; state[3][1] = state[3][0]; state[3][0] = temp;
    }

    void MixColumns(uint8_t state[4][4]) {
        uint8_t tmp[4];
        for (int c = 0; c < 4; c++) {
            for (int i = 0; i < 4; i++) tmp[i] = state[i][c];
            state[0][c] = xtime(tmp[0]) ^ (xtime(tmp[1]) ^ tmp[1]) ^ tmp[2] ^ tmp[3];
            state[1][c] = tmp[0] ^ xtime(tmp[1]) ^ (xtime(tmp[2]) ^ tmp[2]) ^ tmp[3];
            state[2][c] = tmp[0] ^ tmp[1] ^ xtime(tmp[2]) ^ (xtime(tmp[3]) ^ tmp[3]);
            state[3][c] = (xtime(tmp[0]) ^ tmp[0]) ^ tmp[1] ^ tmp[2] ^ xtime(tmp[3]);
        }
    }

public:
    std::vector<uint8_t> encryptBlock(const std::vector<uint8_t>& plaintext, const std::vector<uint8_t>& key) {
        KeyExpansion(key);
        uint8_t state[4][4];
        for (int i = 0; i < 16; i++) state[i % 4][i / 4] = plaintext[i];
        AddRoundKey(state, 0);
        for (int round = 1; round < Nr; round++) {
            SubBytes(state); ShiftRows(state); MixColumns(state); AddRoundKey(state, round);
        }
        SubBytes(state); ShiftRows(state); AddRoundKey(state, Nr);
        std::vector<uint8_t> ciphertext(16);
        for (int i = 0; i < 16; i++) ciphertext[i] = state[i % 4][i / 4];
        return ciphertext;
    }
};

const uint8_t AES128::sbox[256] = {
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16
};

const uint8_t AES128::Rcon[11] = {
    0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36
};




class AES128_CTR {
private:
    AES128 aes;
    void incrementCounter(std::vector<uint8_t>& counter) {
        for (int i = 15; i >= 0; --i) {
            if (++counter[i] != 0) break;
        }
    }
public:
    std::vector<uint8_t> process(const std::vector<uint8_t>& data, const std::vector<uint8_t>& key, const std::vector<uint8_t>& iv) {
        std::vector<uint8_t> result(data.size());
        std::vector<uint8_t> counterBlock = iv;
        std::vector<uint8_t> keyStream;
        for (size_t i = 0; i < data.size(); ++i) {
            if (i % 16 == 0) {
                keyStream = aes.encryptBlock(counterBlock, key);
                incrementCounter(counterBlock);
            }
            result[i] = data[i] ^ keyStream[i % 16];
        }
        return result;
    }
};




std::vector<uint8_t> hexToBytes(const std::string& hex) {
    std::vector<uint8_t> bytes;
    for (size_t i = 0; i < hex.length(); i += 2) {
        std::string byteString = hex.substr(i, 2);
        uint8_t byte = (uint8_t)strtol(byteString.c_str(), NULL, 16);
        bytes.push_back(byte);
    }
    return bytes;
}


std::string bytesToHex(const std::vector<uint8_t>& bytes) {
    std::ostringstream oss;
    for (uint8_t b : bytes) {
        oss << std::hex << std::setw(2) << std::setfill('0') << (int)b;
    }
    return oss.str();
}




int main() {
    std::ifstream infile("test_in.txt");
    std::ofstream outfile("test_out_custom.txt");

    if (!infile.is_open() || !outfile.is_open()) {
        std::cerr << "无法打开输入或输出文件！" << std::endl;
        return 1;
    }

    AES128_CTR aes_ctr;
    std::string keyHex, ivHex, plainHex;

    
    while (std::getline(infile, keyHex) && 
           std::getline(infile, ivHex) && 
           std::getline(infile, plainHex)) {
        
        std::vector<uint8_t> key = hexToBytes(keyHex);
        std::vector<uint8_t> iv = hexToBytes(ivHex);
        std::vector<uint8_t> plaintext = hexToBytes(plainHex);

        std::vector<uint8_t> ciphertext = aes_ctr.process(plaintext, key, iv);
        
        outfile << bytesToHex(ciphertext) << std::endl;
    }

    infile.close();
    outfile.close();
    return 0;
}
// EVOLVE-BLOCK-END
