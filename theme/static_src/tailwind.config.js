/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        '../templates/**/*.html',
        '../../templates/**/*.html',
        '../../**/templates/**/*.html', // <-- Esto debería cubrirlo, pero asegurémonos abajo:
        '../../usuarios/templates/**/*.html', // Fuerza el escaneo de la app usuarios
        '../../reportador/templates/**/*.html', // Fuerza el escaneo de la app reportador
        '../../**/static/**/*.js',
        '../../static/**/*.js',
    ],
    theme: {
        extend: {
            colors: {
                // Paleta de colores empresariales integrados de manera profesional
                brand: {
                    emerald: '#01A684', // Color corporativo primario (Esmeralda)
                    navy: '#0b57a3',    // Color corporativo secundario (Azul Marino)
                    
                    // Variantes de soporte calculadas para estados interactivos (hover, active) y fondos
                    'emerald-light': '#34b89d',
                    'emerald-dark': '#01856a',
                    'navy-light': '#1e6ebf',
                    'navy-dark': '#08437e',
                }
            },
            fontFamily: {
                // Tipografía optimizada para una excelente legibilidad en aplicaciones de datos y gestión
                sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'],
            },
        },
    },
    plugins: [
        /**
         * Plugins esenciales integrados por django-tailwind para el desarrollo de formularios y layouts
         */
        require('@tailwindcss/forms'),
        require('@tailwindcss/typography'),
        require('@tailwindcss/aspect-ratio'),
    ],
}