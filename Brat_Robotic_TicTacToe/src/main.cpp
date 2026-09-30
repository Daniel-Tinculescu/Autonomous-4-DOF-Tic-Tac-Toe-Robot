#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>
#include <stdlib.h>

volatile uint16_t pulseBase   = 1500;
volatile uint16_t pulseShL    = 1500;
volatile uint16_t pulseShR    = 1500;
volatile uint16_t pulseElbow  = 1500;
volatile uint16_t pulsgeWrist  = 1500;

volatile char rx_buffer[32];
volatile uint8_t rx_idx = 0;
volatile uint8_t packet_ready = 0;

void init_gpio() {
    DDRD |= (1 << PD5) | (1 << PD6);
    DDRB |= (1 << PB1) | (1 << PB2) | (1 << PB3);
}

void init_uart() {
    //baud rate 9600 <=> frecventa 16MHz Arduino Uno
    UBRR0H = 0;
    UBRR0L = 103; 
    
    //activare RX, TX si intrerupere de receptie
    UCSR0B = (1 << RXEN0) | (1 << TXEN0) | (1 << RXCIE0); 
    
    //8 biti de date, 1 bit de stop
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00); 
}

void init_timer1() {
    //normal mode
    TCCR1A = 0;

    //prescaler 8 => 1 tick = 0.5ms
    TCCR1B = (1 << CS11);
}

void delay_us_timer(uint16_t us) {
    TCNT1 = 0;
    uint16_t target_ticks = us * 2;
    while (TCNT1 < target_ticks);
}

void update_angles(int b, int u, int e, int w) {
    if (b < 10) {
      b = 10;
    } else if (b > 170) {
      b = 170;
    }

    if (u < 10) {
      u = 10;
    } else if (u > 170) {
      u = 170;
    }

    if (e < 10) {
      e = 10;
    } else if (e > 170) {
      e = 170;
    }

    if (w < 10) {
      w = 10; 
    } else if (w > 170) {
      w = 170;
    }

    //mapare unghi servo (0-180 grade) in latime de impuls PWM (544us - 2400us) standard
    pulseBase  = 544 + ((uint32_t)b * 1856) / 180;
    pulseShL   = 544 + ((uint32_t)u * 1856) / 180;
    pulseShR   = 544 + ((uint32_t)(180 - u) * 1856) / 180; //oglindire umar drept
    pulseElbow = 544 + ((uint32_t)e * 1856) / 180;
    pulseWrist = 544 + ((uint32_t)w * 1856) / 180;
}

// intrerupere hardware pt receptie seriala
ISR(USART_RX_vect) {
    //citim litera din registrul hardware
    char c = UDR0;
    
    if (c == '\n') { //am ajuns la capatul comenzii (exemplu "120,90,10,44\n")
        rx_buffer[rx_idx] = '\0';
        packet_ready = 1;
    } else if (c != '\r' && rx_idx < sizeof(rx_buffer) - 1 && !packet_ready) {
        rx_buffer[rx_idx++] = c; //salvam caracterul în buffer
    }
}

int main(void) {
    init_gpio();
    init_uart();
    init_timer1();
    sei(); //activam intreruperile globale

    update_angles(120, 90, 10, 44);

    while (1) {        
        if (packet_ready) {
            char* ptr = (char*)rx_buffer;
            int b = atoi(ptr);
            while (*ptr && *ptr != ',') ptr++; if (*ptr == ',') ptr++;
            int u = atoi(ptr);
            while (*ptr && *ptr != ',') ptr++; if (*ptr == ',') ptr++;
            int e = atoi(ptr);
            while (*ptr && *ptr != ',') ptr++; if (*ptr == ',') ptr++;
            int w = atoi(ptr);

            update_angles(b, u, e, w);
            
            rx_idx = 0;
            packet_ready = 0;
        }

        
        PORTD |= (1 << PD5);
        delay_us_timer(pulseBase);
        PORTD &= ~(1 << PD5);

        PORTD |= (1 << PD6);
        delay_us_timer(pulseShL);
        PORTD &= ~(1 << PD6);

        PORTB |= (1 << PB1);
        delay_us_timer(pulseShR);
        PORTB &= ~(1 << PB1);

        PORTB |= (1 << PB2); 
        delay_us_timer(pulseElbow);
        PORTB &= ~(1 << PB2);  

        PORTB |= (1 << PB3); 
        delay_us_timer(pulseWrist);
        PORTB &= ~(1 << PB3); 

        _delay_ms(10); 
    }

    return 0;
}