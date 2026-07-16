'use strict'

const path = require('path')
const webpack = require('webpack')
const CopyWebpackPlugin = require('copy-webpack-plugin')
const universalviewerVersion =
    require('./package.json').dependencies['universalviewer']

const config = {
    context: path.join(__dirname, 'appjs'),

    entry: {
        'portal-francearchives': ['./portal-francearchives'],
        'pnia-archivists': ['./pnia-archivists.js'],
        'pnia-search': ['./pnia-search'],
        'fa-context': ['./fa-context'],
        'circular-table': ['./circulars/index.tsx'],
        'pnialocation-map': ['./pnialocation-map'],
        'pniaservices-map': ['./pniaservices-map'],
        'pnia-entity-map': ['./pnia-entity-map'],
        glossary: ['./glossary'],
        'pnia-glossary': ['./pnia-glossary'],
        'pnia-articles': ['./pnia-articles'],
        'intro-tour': ['./introjs'],
        'pnia-mirador': ['./pnia-mirador.tsx'],
        'pnia-iiif-viewers': ['./pnia-iiif-viewers.tsx'],
        'pnia-universalviewer': ['./pnia-universalviewer.tsx'],
        'advanced-search': ['./advanced-search/main.tsx'],
        yasgui: ['./yasgui/index.tsx'],
        sparnatural: ['./sparnatural/index.tsx'],
        'pnia-webchat': ['./pnia-webchat.js'],
    },
    module: {
        strictExportPresence: false,
        rules: [
            {
                test: /\.js$/,
                exclude: /node_modules/,
                loader: 'babel-loader',
                options: {
                    cacheDirectory: true,
                },
            },
            {
                test: [/\.tsx?$/],
                exclude: /node_modules/,
                use: ['ts-loader'],
            },
            {
                test: [/\.jsx?$/],
                exclude: /node_modules/,
                use: ['babel-loader'],
            },
            {
                test: /\.css$/,
                use: ['style-loader', 'css-loader'],
            },
            {
                test: /\.svg$/,
                type: 'asset/resource',
            },
        ],
    },
    output: {
        filename: 'bundle-[name].js',
        path: path.join(__dirname, 'cubicweb_francearchives', 'data'),
    },
    plugins: [
        new webpack.IgnorePlugin({
            resourceRegExp: /^(buffertools)$/,
        }), // unwanted "deeper" dependency
        new CopyWebpackPlugin({
            patterns: [
                {
                    from: '../node_modules/tarteaucitronjs/tarteaucitron.js',
                    to: 'tarteaucitron/tarteaucitron.js',
                },
            ],
        }),
        new webpack.DefinePlugin({
            'process.env.PACKAGE_VERSION': JSON.stringify(
                universalviewerVersion,
            ),
        }),
    ],
    resolve: {
        fallback: {
            url: false,
            '@blueprintjs/core': false,
            '@blueprintjs/icons': false,
        },
        // don't include a normalize-url for mirador, if neededfall back on an other polyfill
        // also get ride of warnings on unused '@blueprintjs/core' and  '@blueprintjs/icons'
        extensions: ['.ts', '.tsx', '.js', '.json'],
    },
}

module.exports = (env, argv) => {
    if (argv.mode === 'production') {
        // install polyfills for production
        config.plugins.push(
            new webpack.DefinePlugin({
                'process.env': {
                    NODE_ENV: JSON.stringify('production'),
                },
            }),
        )
    }

    return config
}
