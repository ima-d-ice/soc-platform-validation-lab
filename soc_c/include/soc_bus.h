/* SoC bus errors: C equivalent of soc/bus BusError.
 *
 * Python raises BusError; C returns SOC_ERR_BUS (-100) so it never
 * collides with peripheral statuses (e.g. UART_ERR_DISABLED=-1).
 */
#ifndef SOC_C_BUS_H
#define SOC_C_BUS_H

#define SOC_OK 0
#define SOC_ERR_BUS (-100)

#endif /* SOC_C_BUS_H */
