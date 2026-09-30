import cv2
import numpy as np
import serial
import time
import os

try:
    arduino = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
    time.sleep(2)
    print("conexiune arduino reusita")
except Exception as e:
    print(f"eroare conexiune Arduino: {e}")
    arduino = None

INCHEIETURA = 44
RETRAGERE_BAZA = 18

def trimite(b, u, c, pauza=0.2):
    if arduino:
        try:
            arduino.write(f"{int(b)},{int(u)},{int(c)},{INCHEIETURA}\n".encode('utf-8'))
        except:
            pass
    print(f"  -> Baza: {b:3} | Umar: {u:3} | Cot: {c:3}")
    time.sleep(pauza)

def tranzitie_baza_in_lant(b_start, b_stop, u, c):
    if b_start == b_stop:
        trimite(b_start, u, c, 0.1)
        return
    pas = 2 if b_start < b_stop else -2
    for b in range(b_start, b_stop + (1 if pas > 0 else -1), pas):
        trimite(b, u, c, 0.1)

unghiuri_celule = {
    1: {'dp': (98,  102, 86,  94),  'ds': (98, 98,  80,  94)},
    2: {'dp': (102, 92,  70,  82),  'ds': (102, 90,  68,  78)},
    3: {'dp': (106, 78,  52,  70),  'ds': (104, 74,  46,  60)},
    4: {'dp': (100, 100, 100, 90),  'ds': (100, 96,  94, 106)},
    5: {'dp': (104, 88,  82,  80),  'ds': (104, 84,  78,  90)},
    6: {'dp': (106, 74,  60,  66),  'ds': (104, 70,  54,  70)},
    7: {'dp': (102, 94,  108, 84),  'ds': (102, 92, 104, 116)},
    8: {'dp': (104, 82,  90,  72),  'ds': (106, 78,  84,  98)},
    9: {'dp': (108, 70,  70,  62),  'ds': (108, 68,  64,  78)},
}

IDX_TO_CELULA = {i: i + 1 for i in range(9)}

def deseneaza_x(celula_nr, baza_curenta=120):
    print(f"\n[{'='*30}]")
    print(f"[  DESENEZ X IN CELULA {celula_nr}  ]")
    print(f"[{'='*30}]")
    dp = unghiuri_celule[celula_nr]['dp']
    ds = unghiuri_celule[celula_nr]['ds']
    
    b_dp, u_start_dp, c_dp, u_stop_dp = dp
    tranzitie_baza_in_lant(baza_curenta, b_dp, u_start_dp, c_dp)
    for u in range(u_start_dp, u_stop_dp - 1, -2):
        trimite(b_dp, u, c_dp)
    baza_curenta = b_dp + RETRAGERE_BAZA
    tranzitie_baza_in_lant(b_dp, baza_curenta, u_stop_dp, c_dp)
    
    b_ds, u_ds, c_start_ds, c_stop_ds = ds
    tranzitie_baza_in_lant(baza_curenta, b_ds, u_ds, c_start_ds)
    for c in range(c_start_ds, c_stop_ds + 1, 2):
        trimite(b_ds, u_ds, c)
    baza_curenta = b_ds + RETRAGERE_BAZA
    tranzitie_baza_in_lant(b_ds, baza_curenta, u_ds, c_stop_ds)
    
    return baza_curenta

#  COMPUTER VISION 

last_valid_coords = None

def extract_grila(frame):
    global last_valid_coords
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    bw = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image = frame.copy()

    min_x, min_y, max_x, max_y = 9999, 9999, 0, 0
    ink = False
    
    for c in contours:
        if cv2.contourArea(c) > 100: 
            x, y, w, h = cv2.boundingRect(c)
            min_x, min_y = min(min_x, x), min(min_y, y)
            max_x, max_y = max(max_x, x + w), max(max_y, y + h)
            ink = True

    area = (max_x - min_x) * (max_y - min_y) if ink else 0

    if ink and area > 15000:
        if last_valid_coords is None:
            last_valid_coords = [min_x, min_y, max_x, max_y]
        else:
            alpha = 0.15 
            last_valid_coords[0] = int(alpha * min_x + (1 - alpha) * last_valid_coords[0])
            last_valid_coords[1] = int(alpha * min_y + (1 - alpha) * last_valid_coords[1])
            last_valid_coords[2] = int(alpha * max_x + (1 - alpha) * last_valid_coords[2])
            last_valid_coords[3] = int(alpha * max_y + (1 - alpha) * last_valid_coords[3])

    if last_valid_coords is not None:
        rx1, ry1, rx2, ry2 = last_valid_coords
        cv2.rectangle(image, (rx1, ry1), (rx2, ry2), (0, 255, 0), 3)
        
        if ry2 > ry1 and rx2 > rx1:
            grila = frame[ry1:ry2, rx1:rx2]
            return cv2.resize(grila, (450, 450)), image

    return None, image


def classify_cell(cell_img):
    gray = cv2.cvtColor(cell_img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 3
    )
    
    MARGIN = 18
    roi = thresh[MARGIN:150-MARGIN, MARGIN:150-MARGIN]

    kernel = np.ones((2, 2), np.uint8)
    roi_curatat = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)

    ink_pixels = cv2.countNonZero(roi_curatat)
    if ink_pixels < 250:
        return ' '

    contours, _ = cv2.findContours(roi_curatat, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [c for c in contours if cv2.contourArea(c) > 80] 
    
    if not valid_contours:
        return ' '

    all_pts = np.concatenate(valid_contours)
    x, y, w, h = cv2.boundingRect(all_pts)

    if w < 15 or h < 15:
        return ' ' 

    glyph = roi_curatat[y:y+h, x:x+w]

    step_x, step_y = w / 3.0, h / 3.0
    densities = np.zeros((3, 3))

    for r in range(3):
        for c in range(3):
            r_start, r_end = int(r * step_y), int((r + 1) * step_y)
            c_start, c_end = int(c * step_x), int((c + 1) * step_x)

            cell_roi = glyph[r_start:r_end, c_start:c_end]
            area = cell_roi.shape[0] * cell_roi.shape[1]
            if area > 0:
                densities[r, c] = cv2.countNonZero(cell_roi) / area

    dens_centru = densities[1, 1]
    dens_colturi = np.mean([densities[0, 0], densities[0, 2], densities[2, 0], densities[2, 2]])
    dens_muchii = np.mean([densities[0, 1], densities[1, 0], densities[1, 2], densities[2, 1]])

    if dens_centru > (dens_muchii + 0.1): 
        return 'X'
    elif dens_muchii > (dens_centru + 0.05):
        return 'O'
    else:
        if dens_colturi > dens_muchii:
            return 'X'
        else:
            return 'O'

def analizeaza_grila(grila_imagine, board_cunoscut):
    debug_img = grila_imagine.copy()
    board = board_cunoscut[:] 

    for row in range(3):
        for col in range(3):
            idx = row * 3 + col
            y1, y2 = row * 150, (row + 1) * 150
            x1, x2 = col * 150, (col + 1) * 150
            
            if board_cunoscut[idx] != ' ':
                symbol = board_cunoscut[idx]
                board[idx] = symbol
            else:
                symbol = classify_cell(grila_imagine[y1:y2, x1:x2])
                board[idx] = symbol

            if symbol == 'X':
                color = (0, 0, 255)
            elif symbol == 'O':
                color = (255, 100, 0)
            else:
                color = (80, 80, 80)

            cv2.rectangle(debug_img, (x1+2, y1+2), (x2-2, y2-2), color, 2)
            cv2.putText(debug_img, symbol, (x1+55, y1+95),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.8, color, 3)

    return board, debug_img

#  MINIMAX
LINII_CASTIGATOARE = [
    (0,1,2),(3,4,5),(6,7,8),
    (0,3,6),(1,4,7),(2,5,8),
    (0,4,8),(2,4,6),
]

def verifica_castigator(board):
    for a, b, c in LINII_CASTIGATOARE:
        if board[a] == board[b] == board[c] != ' ':
            return board[a]
    return None

def e_tabla_plina(board):
    return ' ' not in board

def minimax(board, depth, is_maximizing):
    w = verifica_castigator(board)
    if w == 'X': return 10 - depth
    if w == 'O': return depth - 10
    if e_tabla_plina(board): return 0
    
    if is_maximizing:
        best = -100
        for i in range(9):
            if board[i] == ' ':
                board[i] = 'X'
                best = max(best, minimax(board, depth+1, False))
                board[i] = ' '
        return best
    else:
        best = 100
        for i in range(9):
            if board[i] == ' ':
                board[i] = 'O'
                best = min(best, minimax(board, depth+1, True))
                board[i] = ' '
        return best

def gaseste_mutare_robot(board):
    best_score, best_idx = -100, -1
    for i in range(9):
        if board[i] == ' ':
            board[i] = 'X'
            score = minimax(board, 0, False)
            board[i] = ' '
            if score > best_score:
                best_score, best_idx = score, i
    return best_idx

#  UTILITARE JOC
def afiseaza_tabla(board):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n=== STARE TABLA DE JOC ===")
    for r in range(3):
        print(f"  {board[r*3]} | {board[r*3+1]} | {board[r*3+2]}")
        if r < 2: print("  ---------")
    print("==========================")

def boards_identice(b1, b2):
    if b1 is None or b2 is None: return False
    return all(b1[i] == b2[i] for i in range(9))

def detecteaza_mutare_noua(board_vechi, board_nou):
    diferente = []
    for i in range(9):
        if board_vechi[i] != board_nou[i]:
            if board_vechi[i] != ' ' and board_nou[i] == ' ':
                return -1  
            diferente.append(i)
    if len(diferente) != 1: return -1
    idx = diferente[0]
    return idx if (board_vechi[idx] == ' ' and board_nou[idx] == 'O') else -1

# camera reconnect  
def deschide_camera(idx=1, retries=5):
    for i in range(retries):
        cam = cv2.VideoCapture(idx)
        if cam.isOpened():
            cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cam
        cam.release()
        print(f"retry camera {i+1}/{retries}...")
        time.sleep(1)
    return None

def citeste_frame(cam):
    ret, frame = cam.read()
    if ret:
        return cam, frame
    print("camera pierduta, reconnect...")
    cam.release()
    time.sleep(1)
    cam_noua = deschide_camera()
    if cam_noua is None:
        return None, None
    ret, frame = cam_noua.read()
    return cam_noua, (frame if ret else None)

def ruleaza_joc():
    cam = deschide_camera()
    if cam is None:
        print("Nu se poate accesa camera")
        return

    baza_curenta = 120
    tranzitie_baza_in_lant(120, 120, 90, 10)
    time.sleep(1)

    board = [' '] * 9
    stare = 'robot_muta'
    CONFIRMARE_NECESARA = 15
    confirmare_counter = 0
    board_candidat = None

    print("\n╔══════════════════════════════════╗")
    print("║   BRAT ROBOTIC X&O - START JOC   ║")
    print("║   Robot = X  |  Om = O           ║")
    print("╚══════════════════════════════════╝\n")

    while True:
        cam, frame = citeste_frame(cam)
        if cam is None or frame is None:
            print("Cameră indisponibilă, oprire.")
            break

        h, w, _ = frame.shape
        frame = frame[int(h*0.15):int(h*0.85), int(w*0.20):int(w*0.80)]

        grila, image = extract_grila(frame)
        cv2.imshow('Live Camera', image)

        board_detectat = None
        processed = None
        if grila is not None:
            board_detectat, processed = analizeaza_grila(grila, board)
            cv2.imshow('Robot Vision', processed)


        if stare == 'robot_muta':
            mutare_idx = gaseste_mutare_robot(board)
            celula_nr  = IDX_TO_CELULA[mutare_idx]
            board[mutare_idx] = 'X'
            afiseaza_tabla(board)
            print(f"\n🤖 Robotul muta in celula {celula_nr} (index {mutare_idx})")

            baza_curenta = deseneaza_x(celula_nr, baza_curenta)
            tranzitie_baza_in_lant(baza_curenta, 120, 90, 10)
            baza_curenta = 120

            if verifica_castigator(board):
                print("\n🏆 Robotul a castigat!")
                stare = 'joc_terminat'
            elif e_tabla_plina(board):
                print("\n🤝 Remiza!")
                stare = 'joc_terminat'
            else:
                print("\n⏳ Randul tau! Deseneaza O...")
                stare = 'asteapta_om'
                confirmare_counter = 0
                board_candidat = None

        elif stare == 'asteapta_om':
            if board_detectat is not None:
                mutare_om = detecteaza_mutare_noua(board, board_detectat)
                if mutare_om != -1:
                    if boards_identice(board_detectat, board_candidat):
                        confirmare_counter += 1
                    else:
                        board_candidat = board_detectat[:]
                        confirmare_counter = 1

                    if processed is not None:
                        overlay = processed.copy()
                        pct = int(confirmare_counter / CONFIRMARE_NECESARA * 100)
                        cv2.putText(overlay, f"Confirmare: {pct}%",
                                    (10, 440), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.9, (0, 220, 0), 2)
                        cv2.imshow('Robot Vision', overlay)

                    if confirmare_counter >= CONFIRMARE_NECESARA:
                        board[mutare_om] = 'O'
                        afiseaza_tabla(board)
                        print(f"\n✅ Mutare om confirmata: index {mutare_om}")
                        confirmare_counter = 0
                        board_candidat = None

                        if verifica_castigator(board):
                            print("\n🏆 Omul a castigat!")
                            stare = 'joc_terminat'
                        elif e_tabla_plina(board):
                            print("\n🤝 Remiza!")
                            stare = 'joc_terminat'
                        else:
                            stare = 'robot_muta'
                else:
                    confirmare_counter = 0
                    board_candidat = None

        elif stare == 'joc_terminat':
            if processed is not None:
                overlay = processed.copy()
                c = verifica_castigator(board)
                msg = (f"{'Robot' if c=='X' else 'Om'} a castigat!" if c else "Remiza!")
                cv2.putText(overlay, msg, (55, 230),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,255,255), 3)
                cv2.imshow('Robot Vision', overlay)
            print("\nApasă 'r' pentru o nouă partidă sau 'q' pentru ieșire.")

        key = cv2.waitKey(30) & 0xFF
        if key == ord('q'):
            print("Program oprit.")
            break
        elif key == ord('r') and stare == 'joc_terminat':
            board = [' '] * 9
            stare = 'robot_muta'
            baza_curenta = 120
            # Corectura aici:
            tranzitie_baza_in_lant(baza_curenta, 120, 90, 10) 
            time.sleep(1)
            confirmare_counter = 0
            board_candidat = None
            print("\n🔄 Joc nou!")

    cam.release()
    cv2.destroyAllWindows()
    if arduino:
        arduino.close()

if __name__ == '__main__':
    ruleaza_joc()